package fr.azk.kotoba

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.provider.OpenableColumns
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.activity.result.ActivityResult
import app.tauri.annotation.ActivityCallback
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import java.security.KeyStore
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

@InvokeArg class SavePairingArgs { var code: String = ""; var endpoint: String = "" }
@InvokeArg class PickFileArgs { var kind: String = "source" }
@InvokeArg class SaveFileArgs { var path: String = ""; var filename: String = "translation.json"; var data: String = "" }

@TauriPlugin
class KotobaPlugin(private val activity: Activity): Plugin(activity) {
    private val executor = Executors.newSingleThreadExecutor()
    private val preferences get() = activity.getSharedPreferences("kotoba-private",Context.MODE_PRIVATE)
    private fun key(): SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("kotoba-pairing-v1",null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("kotoba-pairing-v1",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    @Command fun savePairing(invoke: Invoke) { executor.execute {
        try {
            val args=invoke.parseArgs(SavePairingArgs::class.java)
            require(args.code.length<=16384 && args.endpoint.length<=512)
            if(args.code.isEmpty()) { check(preferences.edit().clear().commit()) }
            else {
                val cipher=Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.ENCRYPT_MODE,key())
                val value=JSObject().put("code",args.code).put("endpoint",args.endpoint).toString()
                val encrypted=cipher.iv+cipher.doFinal(value.toByteArray(Charsets.UTF_8))
                check(preferences.edit().putString("encrypted",Base64.encodeToString(encrypted,Base64.NO_WRAP)).commit())
            }
            invoke.resolve(JSObject())
        } catch(_:Exception) { invoke.reject("Impossible de conserver la connexion chiffrÃ©e") }
    } }
    @Command fun loadPairing(invoke: Invoke) { executor.execute {
        try {
            val stored=preferences.getString("encrypted",null)
            if(stored==null) { invoke.resolve(JSObject().put("code","").put("endpoint","")); return@execute }
            val bytes=Base64.decode(stored,Base64.NO_WRAP)
            require(bytes.size>28)
            val cipher=Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,bytes.copyOfRange(0,12)))
            invoke.resolve(JSObject(String(cipher.doFinal(bytes.copyOfRange(12,bytes.size)),Charsets.UTF_8)))
        } catch(_:Exception) { invoke.reject("Connexion enregistrÃ©e illisible. Importez Ã  nouveau le code du PC.") }
    } }
    @Command fun pickFile(invoke: Invoke) {
        val intent=Intent(Intent.ACTION_OPEN_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE); type="*/*" }
        startActivityForResult(invoke,intent,"picked")
    }
    @ActivityCallback fun picked(invoke:Invoke,result:ActivityResult) {
        val uri=result.data?.data
        if(result.resultCode!=Activity.RESULT_OK || uri==null) { invoke.resolve(JSObject().put("cancelled",true)); return }
        executor.execute {
            try {
                var name="document.json"
                activity.contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME),null,null,null)?.use { cursor ->
                    if(cursor.moveToFirst()) name=cursor.getString(0)
                }
                val kind=invoke.parseArgs(PickFileArgs::class.java).kind
                val folder=java.io.File(activity.cacheDir,"kotoba-transfer").apply { mkdirs() }
                val staged=java.io.File.createTempFile("input-",".json",folder)
                var countTotal=0L
                try {
                    activity.contentResolver.openInputStream(uri)?.use { source ->
                        staged.outputStream().use { sink ->
                            val chunk=ByteArray(65536)
                            while(true) {
                                val count=source.read(chunk); if(count<0)break
                                countTotal+=count
                                require(countTotal <= (if(kind=="source") 50L else 2L)*1024*1024) { if(kind=="source") "50 Mo maximum par fichier" else "2 Mo maximum pour le glossaire ou le code" }
                                sink.write(chunk,0,count)
                            }
                        }
                    } ?: error("Fichier inaccessible")
                    if(kind=="source") invoke.resolve(JSObject().put("filename",name).put("size",countTotal).put("path",staged.absolutePath).put("data",""))
                    else {
                        val encoded=Base64.encodeToString(staged.readBytes(),Base64.NO_WRAP)
                        staged.delete()
                        invoke.resolve(JSObject().put("filename",name).put("size",countTotal).put("data",encoded))
                    }
                } catch(e:Exception) { staged.delete(); throw e }

            } catch(e:Exception) { invoke.reject(e.message?:"Lecture impossible") }
        }
    }
    @Command fun saveFile(invoke:Invoke) {
        val args=invoke.parseArgs(SaveFileArgs::class.java)
        if(args.data.length>140*1024*1024) { invoke.reject("RÃ©sultat trop grand"); return }
        val intent=Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE); type="application/json"; putExtra(Intent.EXTRA_TITLE,args.filename.take(180))
        }
        startActivityForResult(invoke,intent,"saved")
    }
    @ActivityCallback fun saved(invoke:Invoke,result:ActivityResult) {
        val uri=result.data?.data
        if(result.resultCode!=Activity.RESULT_OK || uri==null) { invoke.resolve(JSObject().put("cancelled",true)); return }
        executor.execute {
            try {
                val args=invoke.parseArgs(SaveFileArgs::class.java)
                val folder=java.io.File(activity.cacheDir,"kotoba-transfer").canonicalFile
                val source=java.io.File(args.path).canonicalFile
                require(source.parentFile==folder && source.name.startsWith("output-")) { "Fichier de sortie invalide" }
                activity.contentResolver.openOutputStream(uri,"wt")?.use { sink -> source.inputStream().use { it.copyTo(sink,65536) } } ?: error("Destination inaccessible")
                source.delete()
                invoke.resolve(JSObject().put("saved",true))
            } catch(e:Exception) { invoke.reject(e.message?:"Enregistrement impossible") }
        }
    }
}
