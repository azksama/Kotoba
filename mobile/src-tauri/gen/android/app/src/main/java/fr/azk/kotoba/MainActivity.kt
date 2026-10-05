package fr.azk.kotoba

import android.os.Bundle
import android.content.res.Configuration
import androidx.activity.enableEdgeToEdge

class MainActivity : TauriActivity() {
  override fun onConfigurationChanged(newConfig: Configuration) {
    super.onConfigurationChanged(newConfig)
    enableEdgeToEdge()
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
  }
}
