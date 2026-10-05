use serde_json::Value;
#[cfg(target_os="android")]
use tauri::{plugin::{Builder,PluginHandle,TauriPlugin},Manager,Wry};

#[cfg(target_os="android")]
struct Native(PluginHandle<Wry>);
#[cfg(target_os="android")]
pub fn init()->TauriPlugin<Wry> {
    Builder::new("kotoba-native").setup(|app,api| {
        app.manage(Native(api.register_android_plugin("fr.azk.kotoba","KotobaPlugin")?));
        Ok(())
    }).build()
}

#[tauri::command]
pub async fn native_action(app:tauri::AppHandle,op:String,body:Option<Value>)->Result<Value,String> {
    if !["loadPairing","savePairing","pickFile","saveFile"].contains(&op.as_str()) { return Err("Action inconnue".into()); }
    #[cfg(target_os="android")]
    return tauri::async_runtime::spawn_blocking(move || {
        let mut result:Value=app.state::<Native>().0.run_mobile_plugin(&op,body.unwrap_or(serde_json::json!({}))).map_err(|e|e.to_string())?;
        if op=="pickFile" {
            if let Some(path)=result.as_object_mut().and_then(|v|v.remove("path")).and_then(|v|v.as_str().map(str::to_owned)) {
                let state=app.state::<crate::ImportedFiles>();
                let mut files=state.0.lock().map_err(|_|"État indisponible".to_string())?;
                for (_,previous) in files.drain() { let _=std::fs::remove_file(previous); }
                let id=uuid::Uuid::new_v4().to_string();
                files.insert(id.clone(),std::path::PathBuf::from(path));
                result["file_id"]=serde_json::json!(id);
            }
        }
        Ok(result)
    }).await.map_err(|e|e.to_string())?;
    #[cfg(not(target_os="android"))]
    { let _=(app,body); Err("Cette fonction utilise le sÃ©lecteur de fichiers Android".into()) }
}
