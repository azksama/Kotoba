use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use std::time::Duration;

pub const MAX_FILE: usize = 50 * 1024 * 1024;

#[derive(Clone, Serialize, Deserialize)]
pub struct Pairing {
    pub version: u8,
    pub endpoint: String,
    pub certificate: String,
    pub token: String,
}

impl Pairing {
    pub fn parse(code: &str) -> Result<Self, String> {
        if code.len() > 16384 { return Err("Code de connexion trop long".into()); }
        let bytes = URL_SAFE_NO_PAD.decode(code.trim().strip_prefix("KTB1.").ok_or("Code KTB1 attendu")?)
            .map_err(|_| "Code de connexion invalide")?;
        let value: Self = serde_json::from_slice(&bytes).map_err(|_| "Code de connexion invalide")?;
        value.validate()?;
        Ok(value)
    }
    pub fn code(&self) -> String {
        format!("KTB1.{}", URL_SAFE_NO_PAD.encode(serde_json::to_vec(self).expect("pairing serialization")))
    }
    pub fn validate(&self) -> Result<(), String> {
        let url = reqwest::Url::parse(&self.endpoint).map_err(|_| "Adresse HTTPS invalide")?;
        if self.version != 1 || url.scheme() != "https" || url.host_str().is_none()
            || !url.username().is_empty() || url.password().is_some() || url.query().is_some()
            || url.fragment().is_some() || url.path() != "/" || self.token.len() != 64
            || !self.token.bytes().all(|b| b.is_ascii_hexdigit()) || self.certificate.len() > 8192 {
            return Err("Connexion HTTPS avec certificat et clé valide requise".into());
        }
        Ok(())
    }
    pub fn client(&self) -> Result<reqwest::Client, String> {
        self.validate()?;
        let cert = reqwest::Certificate::from_pem(self.certificate.as_bytes()).map_err(|_| "Certificat invalide")?;
        reqwest::Client::builder().https_only(true).no_proxy().tls_built_in_root_certs(false)
            .add_root_certificate(cert).redirect(reqwest::redirect::Policy::none())
            .connect_timeout(Duration::from_secs(10)).timeout(Duration::from_secs(60))
            .build().map_err(|e| e.to_string())
    }
}

#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub target: String,
    pub include: Vec<String>,
    pub exclude: Vec<String>,
    pub strict_tokens: bool,
    pub glossary: Option<serde_json::Value>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Submit {
    pub request_id: String,
    pub filename: String,
    pub data: String,
    #[serde(default)]
    pub options: Options,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Job {
    pub id: String,
    pub filename: String,
    pub status: String,
    pub created_at: u64,
    pub done: u64,
    pub total: u64,
    pub message: String,
    pub reviews: Vec<String>,
    pub options: Options,
}

pub fn validate_options(options: &Options) -> Result<(), String> {
    if !["", "en", "fr"].contains(&options.target.as_str()) { return Err("Langue cible invalide".into()); }
    if options.include.len() + options.exclude.len() > 40 || options.include.iter().chain(&options.exclude).any(|v| v.len() > 256 || (!v.is_empty() && !v.starts_with('/'))) {
        return Err("Filtres JSON invalides".into());
    }
    if let Some(value) = &options.glossary {
        let entries = value.as_object().ok_or("Le glossaire doit être un objet JSON")?;
        if entries.len() > 10000 || entries.iter().any(|(k, v)| k.len() > 10000 || v.as_str().is_none_or(|s| s.is_empty() || s.len() > 10000)) {
            return Err("Glossaire trop grand ou invalide".into());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pairing_rejects_http_credentials_path_and_query() {
        for endpoint in ["http://pc:48736", "https://user:pass@pc/", "https://pc/path", "https://pc/?q=x", "https://pc/#x"] {
            let p = Pairing { version: 1, endpoint: endpoint.into(), certificate: "".into(), token: "a".repeat(64) };
            assert!(p.validate().is_err());
        }
    }
    #[test]
    fn pairing_roundtrip() {
        let p = Pairing { version: 1, endpoint: "https://192.168.1.8:48736".into(), certificate: "test".into(), token: "a".repeat(64) };
        assert_eq!(Pairing::parse(&p.code()).unwrap().endpoint, p.endpoint);
    }
    #[test]
    fn options_reject_arbitrary_language_and_invalid_glossary() {
        assert!(validate_options(&Options { target: "--model".into(), ..Default::default() }).is_err());
        assert!(validate_options(&Options { glossary: Some(serde_json::json!({"x":4})), ..Default::default() }).is_err());
    }
}
