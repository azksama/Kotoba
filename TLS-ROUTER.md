# Port 8189 partagé entre Kotoba et Mochi

Le répartiteur `kotoba-tls-router.exe` lit uniquement le ClientHello TLS (SNI). Il n’a accès à aucune clé privée et transmet les octets initiaux à l’identique, puis relaie les deux sens de la connexion.

- Connexion avec le nom DNS Kotoba configuré : compagnon sur `127.0.0.1:48736`.
- Connexion sans SNI (adresses IP des appairages Mochi actuels) : Mochi sur `127.0.0.1:8189`.
- Autre nom DNS, TLS malformé ou ClientHello trop grand : connexion fermée.

Le répartiteur écoute sur l’adresse LAN du PC, port 8189. Mochi écoute uniquement sur la boucle locale, même port. Kotoba écoute uniquement sur la boucle locale, port 48736. Le certificat et le token de chaque application restent indépendants. La redirection Freebox existante TCP 8189 vers le PC peut ainsi être conservée.

## Démarrage sur ce PC

`Demarrer-Kotoba-PC.cmd` démarre le compagnon et le répartiteur quand `.kotoba/network.json` existe. Mochi Studio garde le contrôle de son moteur ; le répartiteur ne lance pas ComfyUI. Un échec de ComfyUI ne signifie pas que le routage TLS est en panne.

Les paramètres Mochi `listenLan` et `sharePublic` sont désactivés : son exposition réseau est désormais assurée par le répartiteur, tandis que son bridge reste local. Les fichiers d’appairage Mochi existants sont conservés. Ne pas réactiver son écoute sur toutes les interfaces tant que le répartiteur utilise le même port.

Kotoba doit importer le nouveau `.kotoba/pairing.txt` après renouvellement du certificat. Utiliser son nom DNS, et non l’adresse IP publique, pour permettre le routage SNI. Les anciennes connexions Mochi par IP continuent d’aller vers Mochi.

`allow-tls-router.ps1`, exécuté en administrateur, autorise uniquement l’exécutable du répartiteur en TCP 8189 dans le pare-feu Windows. La configuration effective de la Freebox doit rediriger ce port vers l’adresse LAN du PC ; réserver cette adresse en DHCP.

## Limites et validation

128 connexions simultanées au maximum, dont 16 par IP ; ClientHello limité à 64 Ko et 5 secondes ; connexion au backend limitée à 3 secondes ; inactivité de lecture de 5 minutes et écriture bloquée de 60 secondes. Ces limites réduisent les abus mais ne remplacent pas une protection contre une saturation du lien Internet. Les WebSockets Mochi doivent conserver leurs messages périodiques.

Les tests Rust couvrent la sélection SNI, le rejet d’un nom inconnu et la conservation exacte d’un ClientHello fragmenté. `scripts/check_tls_router_local.py --lan ADRESSE_LAN [--public]` vérifie les deux certificats et les réponses HTTPS authentifiées réelles. Un test via l’IP publique depuis le LAN ne remplace pas un essai en 4G/5G.

Les sauvegardes de migration sont dans `.kotoba/backups/tls-router-*`, privées. Pour revenir en arrière : arrêter les deux exécutables Kotoba, restaurer la paire certificat/clé et l’appairage Kotoba, restaurer les configurations `config.json` et `studio.json` Mochi depuis cette sauvegarde, retirer `.kotoba/network.json`, puis relancer les applications. Retirer la règle pare-feu du répartiteur si celui-ci n’est plus utilisé. Aucun fichier de travail ni cache n’est supprimé.

Sur ce PC, les trois scripts Mochi `Start-ComfyPocket.ps1`, `Studio-Control.ps1` et `CompanionProcess.ps1` ont également été adaptés pour filtrer les processus par adresse d’écoute : le routeur LAN ne doit pas être confondu avec le bridge local lors d’un arrêt ou redémarrage. Leurs originaux sont dans la sauvegarde de migration ; les restaurer aussi pour annuler la migration. Une mise à jour de Mochi peut remplacer cette adaptation.
