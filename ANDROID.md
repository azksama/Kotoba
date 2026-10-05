# Kotoba sur Android

Kotoba (言葉, « mot » ou « langage ») commande le moteur de traduction de ton PC. Le téléphone ne charge pas le modèle : le GPU du PC exécute TranslateGemma 12B via Ollama.

## Installation

1. Copie `releases/Kotoba-0.1.0-android-aarch64.apk` sur ton téléphone Android 8 ou plus récent (ARM64), puis ouvre-le pour l’installer.
2. Sur le PC, double-clique `Demarrer-Kotoba-PC.cmd`. Ollama et le compagnon démarrent ; le code privé de connexion apparaît dans le Bloc-notes.
3. Transfère `.kotoba/pairing.txt` vers ton téléphone par USB ou un canal privé. Dans Kotoba → **Mon PC**, importe ce fichier puis touche **Connecter le PC**. Le code contient un secret de connexion : ne le publie pas.
4. Utilise l’adresse contenue dans le fichier de connexion. En mode standard, connecte-toi au Wi-Fi du PC ; en mode partagé, le nom DNS et le port 8189 sont déjà inclus.

La règle Windows `Kotoba-PC-HTTPS` autorise seulement le programme compagnon sur ce port depuis le LAN et les plages VPN privées. Sur un autre PC, lance `allow-network.ps1` dans PowerShell administrateur. Aucun accès Internet direct à Ollama n’est nécessaire.

## Traduction

Choisis un JSON, jusqu’à **50 Mo (52 428 800 octets)**, puis **Vérifier le fichier** et **Lancer la traduction**. Le serveur reconstruit le fichier en remplaçant uniquement les valeurs textuelles sélectionnées. Les clés, nombres, espaces, encodage pris en charge et codes reconnus restent préservés. Les transferts Android utilisent des fichiers temporaires privés, pour éviter de copier les gros JSON dans la mémoire de l’interface. Glossaires et codes de connexion : 2 Mo maximum.

Les champs techniques sont exclus par défaut ; les options permettent de sélectionner des chemins JSON et d’importer un glossaire.

Tu peux fermer l’app pendant le traitement. Le PC doit rester allumé, connecté et éveillé. **Historique** retrouve les travaux et permet d’enregistrer le JSON ou le rapport via le sélecteur Android. Une alerte « À relire » signale une traduction par fragments pour conserver les codes : vérifie sa fluidité dans le jeu. Les formats de commandes inconnus nécessitent un contrôle avant réintégration.

Le fichier original n’est pas remplacé. Sur le PC, les travaux sont conservés dans `.kotoba/jobs` et le cache dans `.kotoba/cache.sqlite3`. Une reprise réutilise les segments déjà traduits. Après un redémarrage du compagnon, les travaux interrompus peuvent être relancés.

## Accès extérieur avec la Freebox

Le mode configuré sur ce PC partage le port TCP **8189** avec Mochi par répartition TLS. Consulte [le guide du répartiteur](TLS-ROUTER.md). Importe le nouveau fichier `.kotoba/pairing.txt` : son nom DNS permet de diriger la connexion vers Kotoba. Aucun VPN n'est nécessaire dans ce mode.

Le pare-feu Windows autorise le répartiteur ; la Freebox doit rediriger le port TCP 8189 vers le PC. Ollama reste local. Les deux services ont été vérifiés via l'adresse publique depuis le PC, avec contrôle de leur certificat et de l'authentification. Un essai depuis un téléphone physique en 4G/5G reste nécessaire.

Le mode LAN standard utilise le port 48736 quand `.kotoba/network.json` est absent. Un VPN donnant accès au LAN reste possible avec ce mode.

## Construction

`build-android.ps1 -Target aarch64` reconstruit et signe l’APK. Le script gère l’absence de privilège de création de liens symboliques Windows en copiant la bibliothèque native avant Gradle. Les clés de signature restent dans `.android-signing`, hors archives publiques. Conserve-les pour installer les futures mises à jour sans désinstaller l’app.

Le compagnon se compile avec `cargo build -p kotoba-companion --release` ; copie ensuite `target/release/kotoba-companion.exe` dans `releases/`.

## Validation et limites

Les tests automatisés, le HTTPS avec certificat épinglé et le parcours Android ont été exécutés localement. L’émulateur Android Studio a importé un JSON, déclenché une véritable traduction GPU, retrouvé le résultat après passage en arrière-plan et exporté un JSON valide. Le téléphone physique et la liaison VPN 4G/5G restent à vérifier.
