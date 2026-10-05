mod native;
use base64::{engine::general_purpose::STANDARD, Engine};
use kotoba_protocol::{Pairing, MAX_FILE};
use serde_json::{json, Value};
use std::sync::Mutex;
use tauri::Manager;
#[derive(Default)]
struct ImportedFiles(Mutex<std::collections::HashMap<String,std::path::PathBuf>>);

#[derive(Clone)]
struct Connection { pairing: Pairing, client: reqwest::Client }
#[derive(Default)]
struct Remote(Mutex<Option<Connection>>);

async fn send(connection: &Connection, method: reqwest::Method, path: &str, body: Option<Value>, binary: bool, output_dir: Option<std::path::PathBuf>) -> Result<Value, String> {
    let mut request = connection.client.request(method,format!("{}{}",connection.pairing.endpoint.trim_end_matches('/'),path))
        .bearer_auth(&connection.pairing.token);
    if let Some(ref body)=body { request=request.json(body); }
    let transfer = body.is_some() || binary;
    request = request.timeout(std::time::Duration::from_secs(if transfer { 600 } else { 30 }));
    let mut response = request.send().await.map_err(|e| {
        if e.is_timeout() { "Délai dépassé pendant le transfert. Le PC peut rester connecté ; réessayez sur un réseau plus rapide.".to_owned() }
        else if e.is_connect() { "Connexion au PC impossible. Vérifiez son démarrage et votre connexion Internet.".to_owned() }
        else { "Transfert interrompu. Réessayez ; le fichier original est conservé.".to_owned() }
    })?;
    let status=response.status();
    let mut data=Vec::new();
    while let Some(chunk)=response.chunk().await.map_err(|_|"Téléchargement interrompu")? {
        if data.len()+chunk.len()>MAX_FILE*2 { return Err("Réponse du PC trop volumineuse".into()); }
        data.extend_from_slice(&chunk);
    }
    if !status.is_success() {
        let value: Value=serde_json::from_slice(&data).unwrap_or_default();
        return Err(if status.as_u16()==401 { "Connexion révoquée. Importez un nouveau code depuis le PC.".into() }
            else { value["error"].as_str().unwrap_or("Le PC a refusé la requête").to_owned() });
    }
    if binary {
        let dir=output_dir.ok_or("Dossier de sortie indisponible")?;
        std::fs::create_dir_all(&dir).map_err(|_|"Dossier de sortie indisponible")?;
        let path=dir.join(format!("output-{}.json",uuid::Uuid::new_v4()));
        std::fs::write(&path,data).map_err(|_|"Écriture du résultat impossible")?;
        Ok(json!({"path":path}))
    }
    else { serde_json::from_slice(&data).map_err(|_|"Réponse du PC invalide".into()) }
}

#[tauri::command]
async fn connect(state:tauri::State<'_,Remote>,code:String,endpoint:Option<String>) -> Result<Value,String> {
    let mut pairing=Pairing::parse(&code)?;
    if let Some(endpoint)=endpoint.filter(|s|!s.trim().is_empty()) { pairing.endpoint=endpoint.trim().trim_end_matches('/').to_owned(); }
    let connection=Connection {client:pairing.client()?,pairing};
    let mut health=send(&connection,reqwest::Method::GET,"/v1/health",None,false,None).await?;
    health["endpoint"]=json!(connection.pairing.endpoint);
    *state.0.lock().map_err(|_|"État indisponible")?=Some(connection);
    Ok(health)
}

#[tauri::command]
async fn remote(app:tauri::AppHandle,state:tauri::State<'_,Remote>,op:String,id:Option<String>,mut body:Option<Value>) -> Result<Value,String> {
    let connection=state.0.lock().map_err(|_|"État indisponible")?.clone().ok_or("Connectez d’abord le PC")?;
    let job_id=if let Some(id)=id { Some(uuid::Uuid::parse_str(&id).map_err(|_|"Identifiant invalide")?.to_string()) }else{None};
    let (method,path,binary)=match op.as_str() {
        "health" => (reqwest::Method::GET,"/v1/health".into(),false),
        "list" => (reqwest::Method::GET,"/v1/jobs".into(),false),
        "preview" => (reqwest::Method::POST,"/v1/preview".into(),false),
        "submit" => (reqwest::Method::POST,"/v1/jobs".into(),false),
        "detail"|"cancel"|"retry"|"result"|"report" => {
            let id=job_id.ok_or("Identifiant manquant")?;
            let path=format!("/v1/jobs/{id}{}",if op=="detail"{String::new()}else{format!("/{op}")});
            let method=if op=="cancel"||op=="retry"{reqwest::Method::POST}else{reqwest::Method::GET};
            (method,path,op=="result"||op=="report")
        },
        _=>return Err("Opération inconnue".into()),
    };
    if matches!(op.as_str(),"preview"|"submit") {
        if let Some(value)=body.as_mut() {
            let id=value.as_object_mut().and_then(|o|o.remove("file_id"));
            if let Some(id)=id.and_then(|v|v.as_str().map(str::to_owned)) {
                let file=app.state::<ImportedFiles>().0.lock().map_err(|_|"État indisponible")?.get(&id).cloned().ok_or("Réimportez le fichier")?;
                let data=std::fs::read(file).map_err(|_|"Réimportez le fichier")?;
                if data.len()>MAX_FILE { return Err("50 Mo maximum par fichier".into()); }
                value["data"]=json!(STANDARD.encode(data));
            }
        }
    }
    let folder=app.path().app_cache_dir().map_err(|_|"Cache indisponible")?.join("kotoba-transfer");
    send(&connection,method,&path,body,binary,Some(folder)).await
}

#[tauri::command]
fn disconnect(state:tauri::State<'_,Remote>) { if let Ok(mut connection)=state.0.lock(){*connection=None;} }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder=tauri::Builder::default().manage(Remote::default()).manage(ImportedFiles::default());
    #[cfg(target_os="android")]
    let builder=builder.plugin(native::init());
    builder.invoke_handler(tauri::generate_handler![connect,remote,disconnect,native::native_action])
        .run(tauri::generate_context!()).expect("Kotoba startup failed");
}
