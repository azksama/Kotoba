use axum::{body::Body, extract::{DefaultBodyLimit, Path, Request, State}, http::{header, StatusCode}, middleware::{self, Next}, response::{IntoResponse, Response}, routing::{get, post}, Json, Router};
use base64::{engine::general_purpose::STANDARD, Engine};
use clap::Parser;
use kotoba_protocol::{validate_options, Job, Options, Pairing, Submit, MAX_FILE};
use serde_json::{json, Value};
use std::{collections::BTreeMap, io::Write, net::SocketAddr, path::{Path as FsPath, PathBuf}, sync::Arc, time::{Duration, SystemTime, UNIX_EPOCH}};
use subtle::ConstantTimeEq;
use tokio::{io::{AsyncBufReadExt, BufReader}, process::Command, sync::{mpsc, Mutex}};
use uuid::Uuid;

#[derive(Parser)]
struct Args {
    #[arg(long, default_value = ".kotoba")] data: PathBuf,
    #[arg(long, default_value = "translate_json.py")] translator: PathBuf,
    #[arg(long, default_value = "python")] python: String,
    #[arg(long, default_value = "0.0.0.0:48736")] bind: SocketAddr,
    /// Address written to pairing code, and certificate SAN on first launch.
    #[arg(long, default_value = "localhost")] host: String,
    #[arg(long)] san: Vec<String>,
    #[arg(long)] advertise_port: Option<u16>,
}

struct App {
    root: PathBuf, translator: PathBuf, python: String, token: String,
    jobs: Mutex<BTreeMap<String, Job>>, queue: mpsc::Sender<String>,
    preview: tokio::sync::Semaphore,
}
type Shared = Arc<App>;
type ApiResult<T> = Result<T, ApiError>;
struct ApiError(StatusCode, String);
impl IntoResponse for ApiError { fn into_response(self) -> Response { (self.0, Json(json!({"error": self.1}))).into_response() } }
fn invalid(message: impl Into<String>) -> ApiError { ApiError(StatusCode::BAD_REQUEST, message.into()) }
fn internal(e: impl std::fmt::Display) -> ApiError { eprintln!("Companion error: {e}"); ApiError(StatusCode::INTERNAL_SERVER_ERROR, "Le PC n’a pas pu terminer l’opération. Consultez son journal.".into()) }
fn now() -> u64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs() }
fn save_job(root: &FsPath, job: &Job) -> std::io::Result<()> {
    let path = root.join("jobs").join(&job.id).join("job.json");
    let mut file = atomic_write_file::AtomicWriteFile::open(path)?;
    file.write_all(&serde_json::to_vec_pretty(job)?)?;
    file.commit()
}
fn id_path(app: &App, id: &str) -> ApiResult<PathBuf> {
    let uuid = Uuid::parse_str(id).map_err(|_| invalid("Identifiant invalide"))?;
    if uuid.to_string() != id { return Err(invalid("Identifiant invalide")); }
    Ok(app.root.join("jobs").join(id))
}
fn filename(value: &str) -> String {
    let name = value.rsplit(['/', '\\']).next().unwrap_or("document.json");
    let safe: String = name.chars().filter(|c| !c.is_control() && !"<>:\"|?*".contains(*c)).take(120).collect();
    if safe.is_empty() { "document.json".into() } else { safe }
}
fn command(app: &App, dir: &FsPath, options: &Options, preview: bool) -> Command {
    let mut cmd = Command::new(&app.python);
    cmd.arg("-X").arg("utf8").arg(&app.translator).arg(dir.join("input.json"));
    if preview { cmd.arg("--dry-run"); }
    else { cmd.arg("-o").arg(dir.join("output.json")).arg("--report").arg(dir.join("report.json"))
        .arg("--cache").arg(app.root.join("cache.sqlite3")); }
    cmd.arg("--target").arg(if options.target == "fr" { "French (fr)" } else { "English (en)" });
    if options.strict_tokens { cmd.arg("--strict-tokens"); }
    for path in &options.include { cmd.arg("--include").arg(path); }
    for path in &options.exclude { cmd.arg("--exclude").arg(path); }
    if options.glossary.is_some() { cmd.arg("--glossary").arg(dir.join("glossary.json")); }
    cmd.kill_on_drop(true);
    #[cfg(windows)] cmd.creation_flags(0x08000000);
    cmd
}
async fn prepare(dir: &FsPath, submission: &Submit) -> ApiResult<()> {
    validate_options(&submission.options).map_err(invalid)?;
    if submission.data.len() > MAX_FILE * 4 / 3 + 8 { return Err(ApiError(StatusCode::PAYLOAD_TOO_LARGE, "50 Mo maximum par fichier".into())); }
    let data = STANDARD.decode(&submission.data).map_err(|_| invalid("Fichier encodé invalide"))?;
    if data.is_empty() || data.len() > MAX_FILE { return Err(invalid("Fichier vide ou supérieur à 50 Mo")); }
    tokio::fs::create_dir_all(dir).await.map_err(internal)?;
    tokio::fs::write(dir.join("input.json"), data).await.map_err(internal)?;
    if let Some(glossary) = &submission.options.glossary {
        tokio::fs::write(dir.join("glossary.json"), serde_json::to_vec(glossary).map_err(internal)?).await.map_err(internal)?;
    }
    Ok(())
}
async fn inspect(app: &App, dir: &FsPath, options: &Options) -> ApiResult<Value> {
    let result = tokio::time::timeout(Duration::from_secs(45), command(app, dir, options, true).output()).await
        .map_err(|_| invalid("Analyse trop longue. Réduisez la taille du fichier."))?.map_err(internal)?;
    if !result.status.success() {
        let error = String::from_utf8_lossy(&result.stderr);
        return Err(invalid(error.lines().last().unwrap_or("JSON invalide").chars().take(600).collect::<String>()));
    }
    let text = String::from_utf8_lossy(&result.stdout);
    let first = text.lines().next().unwrap_or_default();
    let total = first.split(',').nth(1).and_then(|s| s.split_whitespace().next()).and_then(|n| n.parse::<u64>().ok()).unwrap_or(0);
    Ok(json!({"total":total, "preview":text.lines().skip(1).take(8).map(|s| s.chars().take(350).collect::<String>()).collect::<Vec<_>>()}))
}
async fn auth(State(app): State<Shared>, req: Request, next: Next) -> Response {
    let bearer = req.headers().get(header::AUTHORIZATION).and_then(|h| h.to_str().ok()).and_then(|v| v.strip_prefix("Bearer ")).unwrap_or("");
    if bearer.as_bytes().ct_eq(app.token.as_bytes()).unwrap_u8() != 1 {
        return (StatusCode::UNAUTHORIZED, Json(json!({"error":"Connexion non autorisée"}))).into_response();
    }
    next.run(req).await
}
async fn health(State(app): State<Shared>) -> Json<Value> {
    let client = reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(3)).build().unwrap();
    let tags = match client.get("http://127.0.0.1:11434/api/tags").send().await { Ok(r) => r.json::<Value>().await.ok(), Err(_) => None };
    let model_ready = tags.as_ref().and_then(|v| v["models"].as_array()).is_some_and(|a| a.iter().any(|m| m["name"] == "ja-en-game:12b"));
    let ps = match client.get("http://127.0.0.1:11434/api/ps").send().await { Ok(r) => r.json::<Value>().await.ok(), Err(_) => None };
    Json(json!({"name":"Kotoba PC", "version":env!("CARGO_PKG_VERSION"), "ollama":tags.is_some(), "model_ready":model_ready,
        "model":"TranslateGemma 12B", "running_models":ps.map(|v|v["models"].clone()), "jobs":app.jobs.lock().await.len(), "max_file_bytes": MAX_FILE}))
}
async fn preview(State(app): State<Shared>, Json(body): Json<Submit>) -> ApiResult<Json<Value>> {
    let _permit = app.preview.try_acquire().map_err(|_| ApiError(StatusCode::TOO_MANY_REQUESTS, "Une analyse est en cours. Réessayez.".into()))?;
    let dir = app.root.join("previews").join(Uuid::new_v4().to_string());
    let result = async { prepare(&dir, &body).await?; inspect(&app, &dir, &body.options).await }.await;
    let _ = tokio::fs::remove_dir_all(&dir).await;
    result.map(Json)
}
async fn submit(State(app): State<Shared>, Json(body): Json<Submit>) -> ApiResult<Json<Job>> {
    let id = Uuid::parse_str(&body.request_id).map_err(|_| invalid("Identifiant de requête invalide"))?.to_string();
    // Serialise submissions/preview validation; request_id makes network retries idempotent.
    let _permit = app.preview.acquire().await.map_err(internal)?;
    {
        let jobs = app.jobs.lock().await;
        if let Some(existing) = jobs.get(&id) { return Ok(Json(existing.clone())); }
        if jobs.len() >= 256 { return Err(ApiError(StatusCode::CONFLICT, "Historique plein : archivez les dossiers de tâches sur le PC après arrêt du serveur.".into())); }
        if jobs.values().filter(|j| j.status == "queued" || j.status == "running").count() >= 32 {
            return Err(ApiError(StatusCode::TOO_MANY_REQUESTS, "La file contient déjà 32 traductions".into()));
        }
    }
    let dir = id_path(&app, &id)?;
    prepare(&dir, &body).await?;
    let inspection = match inspect(&app, &dir, &body.options).await {
        Ok(value) => value,
        Err(error) => { let _ = tokio::fs::remove_dir_all(&dir).await; return Err(error); }
    };
    let job = Job { id: id.clone(), filename: filename(&body.filename), status: "queued".into(), created_at: now(), done: 0,
        total: inspection["total"].as_u64().unwrap_or(0), message: "En attente du PC".into(), reviews: vec![], options: body.options };
    save_job(&app.root, &job).map_err(internal)?;
    app.jobs.lock().await.insert(id.clone(), job.clone());
    app.queue.send(id).await.map_err(internal)?;
    Ok(Json(job))
}
async fn list(State(app): State<Shared>) -> Json<Vec<Job>> {
    let mut jobs: Vec<_> = app.jobs.lock().await.values().cloned().collect();
    jobs.sort_by_key(|j| std::cmp::Reverse(j.created_at));
    Json(jobs)
}
async fn detail(State(app): State<Shared>, Path(id): Path<String>) -> ApiResult<Json<Job>> {
    id_path(&app, &id)?;
    app.jobs.lock().await.get(&id).cloned().map(Json).ok_or(ApiError(StatusCode::NOT_FOUND, "Traduction introuvable".into()))
}
async fn cancel(State(app): State<Shared>, Path(id): Path<String>) -> ApiResult<Json<Job>> {
    id_path(&app, &id)?;
    let mut jobs = app.jobs.lock().await;
    let job = jobs.get_mut(&id).ok_or(ApiError(StatusCode::NOT_FOUND, "Traduction introuvable".into()))?;
    if ["queued", "running"].contains(&job.status.as_str()) {
        job.status = "cancelled".into(); job.message = "Annulée. Le fichier source est conservé.".into();
        save_job(&app.root, job).map_err(internal)?;
    }
    Ok(Json(job.clone()))
}
async fn retry(State(app): State<Shared>, Path(id): Path<String>) -> ApiResult<Json<Job>> {
    let dir = id_path(&app, &id)?;
    let job = app.jobs.lock().await.get(&id).cloned().ok_or(ApiError(StatusCode::NOT_FOUND, "Traduction introuvable".into()))?;
    if ["running", "queued"].contains(&job.status.as_str()) { return Err(invalid("La traduction est déjà active")); }
    let body = Submit { request_id: Uuid::new_v4().to_string(), filename: job.filename,
        data: STANDARD.encode(tokio::fs::read(dir.join("input.json")).await.map_err(internal)?), options: job.options };
    submit(State(app), Json(body)).await
}
async fn result(State(app): State<Shared>, Path(id): Path<String>) -> ApiResult<Response> {
    let dir = id_path(&app, &id)?;
    let job = app.jobs.lock().await.get(&id).cloned().ok_or(ApiError(StatusCode::NOT_FOUND, "Traduction introuvable".into()))?;
    if job.status != "completed" { return Err(ApiError(StatusCode::CONFLICT, "Le résultat n’est pas encore disponible".into())); }
    let data = tokio::fs::read(dir.join("output.json")).await.map_err(internal)?;
    Ok(([(header::CONTENT_TYPE,"application/json"), (header::CACHE_CONTROL,"no-store")], Body::from(data)).into_response())
}
async fn report(State(app): State<Shared>, Path(id): Path<String>) -> ApiResult<Response> {
    let dir = id_path(&app, &id)?;
    let bytes = tokio::fs::read(dir.join("report.json")).await.map_err(|_| ApiError(StatusCode::NOT_FOUND, "Rapport indisponible".into()))?;
    Ok(([(header::CONTENT_TYPE,"application/json"), (header::CACHE_CONTROL,"no-store")], bytes).into_response())
}

async fn mutate(app: &App, id: &str, apply: impl FnOnce(&mut Job)) {
    let mut jobs = app.jobs.lock().await;
    if let Some(job) = jobs.get_mut(id) {
        apply(job);
        if let Err(error) = save_job(&app.root, job) { eprintln!("Persistence error for {id}: {error}"); }
    }
}
async fn run_job(app: &App, id: &str) -> Result<(), String> {
    let job = { let jobs = app.jobs.lock().await; let Some(job) = jobs.get(id) else { return Ok(()); }; if job.status != "queued" { return Ok(()); } job.clone() };
    mutate(app, id, |j| { j.status = "running".into(); j.message = "Chargement du modèle sur le PC…".into(); }).await;
    let dir = app.root.join("jobs").join(id);
    let stderr = std::fs::File::create(dir.join("worker.log")).map_err(|e|e.to_string())?;
    let mut child = command(app, &dir, &job.options, false).stdout(std::process::Stdio::piped()).stderr(stderr).spawn().map_err(|e|e.to_string())?;
    let mut lines = BufReader::new(child.stdout.take().unwrap()).lines();
    loop {
        tokio::select! {
            line = lines.next_line() => {
                let Some(line) = line.map_err(|e|e.to_string())? else { break; };
                if let Some(progress) = line.strip_prefix('[').and_then(|s| s.split(']').next()) {
                    if let Some((done, total)) = progress.split_once('/') {
                        if let (Ok(done), Ok(total)) = (done.parse::<u64>(), total.parse::<u64>()) {
                            mutate(app,id,|j| { j.done=done; j.total=total; j.message=format!("{done} / {total} textes traduits"); }).await;
                        }
                    }
                }
                if line.starts_with("REVIEW ") { mutate(app,id,|j| j.reviews.push(line.chars().take(500).collect())).await; }
            }
            _ = tokio::time::sleep(Duration::from_millis(400)) => {
                let cancelled = app.jobs.lock().await.get(id).is_some_and(|j| j.status=="cancelled");
                if cancelled { let _ = child.kill().await; let _ = child.wait().await; return Ok(()); }
            }
        }
    }
    let status = child.wait().await.map_err(|e|e.to_string())?;
    if !status.success() {
        let error = tokio::fs::read_to_string(dir.join("worker.log")).await.unwrap_or_default();
        return Err(error.lines().last().unwrap_or("La traduction a échoué").chars().take(600).collect());
    }
    if !dir.join("output.json").exists() { return Err("Le résultat est introuvable".into()); }
    mutate(app,id,|j| if j.status != "cancelled" { j.status="completed".into(); j.done=j.total; j.message=if j.reviews.is_empty(){"Traduction terminée".into()}else{"Terminée · passages à relire".into()}; }).await;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _ = rustls::crypto::ring::default_provider().install_default();
    let args = Args::parse();
    std::fs::create_dir_all(args.data.join("jobs"))?;
    let root = args.data.canonicalize()?;
    let translator = args.translator.canonicalize()?;
    let cert_path = root.join("certificate.pem");
    let key_path = root.join("private-key.pem");
    let token_path = root.join("token.txt");
    if !cert_path.exists() && !key_path.exists() {
        let mut sans = vec![args.host.clone(), "localhost".into(), "127.0.0.1".into(), "10.0.2.2".into()];
        sans.extend(args.san); sans.sort(); sans.dedup();
        let rcgen::CertifiedKey { cert, signing_key } = rcgen::generate_simple_self_signed(sans)?;
        std::fs::write(&cert_path, cert.pem())?;
        std::fs::write(&key_path, signing_key.serialize_pem())?;
    }
    if !cert_path.exists() || !key_path.exists() { return Err("Certificate/key incomplete: restore the pair".into()); }
    if !token_path.exists() {
        let token: String = rand::random::<[u8;32]>().iter().map(|b|format!("{b:02x}")).collect();
        std::fs::write(&token_path, token)?;
    }
    let token = std::fs::read_to_string(&token_path)?.trim().to_owned();
    let pairing = Pairing { version:1, endpoint:format!("https://{}:{}", args.host, args.advertise_port.unwrap_or(args.bind.port())), certificate:std::fs::read_to_string(&cert_path)?, token:token.clone() };
    pairing.validate().map_err(std::io::Error::other)?;
    std::fs::write(root.join("pairing.txt"),pairing.code())?;
    let mut jobs = BTreeMap::new();
    for entry in std::fs::read_dir(root.join("jobs"))? {
        let entry = entry?;
        let id = entry.file_name().to_string_lossy().to_string();
        if Uuid::parse_str(&id).is_err() { continue; }
        if let Ok(text) = std::fs::read(entry.path().join("job.json")) {
            if let Ok(mut job) = serde_json::from_slice::<Job>(&text) {
                if job.id != id { continue; }
                if ["running", "queued"].contains(&job.status.as_str()) { job.status="interrupted".into(); job.message="PC redémarré. Relancez pour reprendre via le cache.".into(); save_job(&root,&job)?; }
                jobs.insert(id,job);
            }
        }
    }
    let (queue, mut receiver) = mpsc::channel::<String>(32);
    let app = Arc::new(App { root, translator, python:args.python, token, jobs:Mutex::new(jobs), queue, preview:tokio::sync::Semaphore::new(1) });
    let worker = app.clone();
    tokio::spawn(async move { while let Some(id)=receiver.recv().await { if let Err(error)=run_job(&worker,&id).await {
        mutate(&worker,&id,|j| if j.status!="cancelled" { j.status="failed".into(); j.message=error; }).await;
    } } });
    let router = Router::new().route("/v1/health",get(health)).route("/v1/preview",post(preview))
        .route("/v1/jobs",get(list).post(submit)).route("/v1/jobs/{id}",get(detail))
        .route("/v1/jobs/{id}/cancel",post(cancel)).route("/v1/jobs/{id}/retry",post(retry))
        .route("/v1/jobs/{id}/result",get(result)).route("/v1/jobs/{id}/report",get(report))
        .layer(DefaultBodyLimit::max(72*1024*1024)).layer(middleware::from_fn_with_state(app.clone(),auth)).with_state(app);
    let tls = axum_server::tls_rustls::RustlsConfig::from_pem_file(cert_path,key_path).await?;
    println!("Kotoba PC ready on {} · pairing is in .kotoba/pairing.txt (private)",pairing.endpoint);
    axum_server::bind_rustls(args.bind,tls).serve(router.into_make_service()).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn filename_is_only_a_display_name() { assert_eq!(filename("../../file.json"),"file.json"); assert_eq!(filename("C:\\game\\map.json"),"map.json"); }
    #[test] fn safe_job_id_rejects_traversal() { assert!(Uuid::parse_str("../token.txt").is_err()); }
}
