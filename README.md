# Kotoba — traduction locale de JSON de jeux

Application Android Rust/Tauri et compagnon Windows pour traduire des fichiers JSON de jeux avec le GPU du PC. Limite Android : **50 Mo par fichier**.

[Télécharger la dernière release](https://github.com/azksama/Kotoba/releases/latest) · [Guide Android et Freebox](ANDROID.md)

Sur Windows, décompresse le paquet PC, installe Python 3.10+ si nécessaire, puis exécute `setup-ollama.ps1` et `Demarrer-Kotoba-PC.cmd`. Installe l’APK sur Android et importe le code privé fourni par le PC.

Python 3.10+ et Ollama, sans dépendance Python à installer. Le modèle utilisé est **TranslateGemma 12B Q4_K_M**, sous le nom local `ja-en-game:12b`.

## Utilisation

Ouvrir PowerShell dans ce dossier. Les chemins de fichiers contenant des espaces doivent être entre guillemets.

```powershell
# Voir les champs qui seront traduits, sans appeler le modèle ni écrire de fichier.
.\translate.ps1 "C:\Mon jeu\data\dialogues.json" --dry-run

# Traduire. Le fichier source reste intact.
.\translate.ps1 "C:\Mon jeu\data\dialogues.json" -o "C:\Mon jeu\traduction\dialogues.json"

# Traiter récursivement un dossier de JSON, dans un dossier de sortie séparé.
.\translate.ps1 "C:\Mon jeu\data" -o "C:\Mon jeu\data-en"

# Essai fourni.
.\translate.ps1 .\examples\game.ja.json -o .\outputs\mon-essai.en.json

# Toute l'aide.
.\translate.ps1 --help
```

Si les scripts PowerShell sont bloqués par la politique locale, la commande Python fonctionne directement lorsque l'application Ollama est ouverte :

```powershell
python -X utf8 .\translate_json.py "C:\Mon jeu\data\dialogues.json" -o "C:\Mon jeu\traduction\dialogues.json"
```

## Choisir les champs

Les clés JSON ne sont jamais traduites. Par défaut, seules les **valeurs** contenant des kana ou idéogrammes CJK sont sélectionnées. Les idéogrammes seuls ne permettent pas de distinguer japonais et chinois : les fichiers fournis doivent bien être japonais.

Les sous-arbres sous les clés `id`, `uuid`, `guid`, `path`, `file`, `filename`, `url`, `uri`, `script` et `code` sont exclus par défaut, sans distinction de casse. Les autres chaînes japonaises, y compris les noms de personnages, sont candidates.

Pour un export de jeu inconnu, examiner `--dry-run`, puis cibler les champs textuels. Le script sait lire toute structure JSON standard, mais ne peut pas deviner si une chaîne japonaise est un dialogue, un identifiant de ressource ou un script propre au moteur.

```powershell
# Uniquement les dialogues et les menus. Les options sont répétables.
.\translate.ps1 .\jeu.json --include '/dialogues/*/text' --include '/menu/*'

# Conserver les noms des personnages et les métadonnées.
.\translate.ps1 .\jeu.json --exclude '*/speaker' --exclude '/metadata/*'

# Préserver un autre sous-arbre technique.
.\translate.ps1 .\jeu.json --skip-key resourceName

# Désactiver la liste d'exclusion par défaut, si le schéma l'exige.
.\translate.ps1 .\jeu.json --no-default-skip-keys --include '/code/description'
```

Les filtres utilisent les chemins **JSON Pointer**, avec les jokers Python `fnmatch` (`*` peut traverser plusieurs niveaux). Exemple : `/dialogues/0/text`. Dans les clés, `/` devient `~1` et `~` devient `~0`. Une racine contenant directement une chaîne a pour chemin la chaîne vide.

## Protections

- Clés, nombres (y compris très grands entiers, décimales et notation exponentielle), booléens et `null` conservés tels quels.
- Mise en forme du document et espaces hors des chaînes conservés. Seules les chaînes traduites sont réencodées en JSON avec un échappement valide.
- UTF-8, UTF-8 avec BOM, UTF-16/32 avec BOM : encodage et BOM conservés. Les anciens encodages tels que Shift-JIS doivent être convertis au préalable.
- Variables `{player}`, `${name}`, formats `%d`, `%s`, `%1$s`, `%1`, codes `\V[1]`, `\C[2]`, `\!`, balises HTML simples, entités HTML, tabulations et retours à la ligne protégés.
- Les tokens protégés doivent être rendus une seule fois, dans le même ordre. Une réponse qui les altère est rejetée et retentée. Si le problème persiste, le script traduit les fragments entre les tokens en gardant ceux-ci hors du modèle. Ces phrases sont signalées `REVIEW` et listées dans le rapport : leur fluidité doit être relue, car l'ordre japonais peut subsister. Ajouter `--strict-tokens` pour refuser ce repli et arrêter le fichier à la place.
- Entrées JSON invalides ou contenant des clés dupliquées refusées avant traduction.
- Une réponse tronquée, vide, un bloc Markdown ou une traduction identique au texte source est refusée.
- Un échec interrompt le traitement, avec un code de sortie non nul. Le fichier en échec n'est pas publié. Les fichiers déjà réussis et le cache restent disponibles.

Ajouter les codes propres à un moteur :

```powershell
.\translate.ps1 .\jeu.json --protect-regex '\[wait=\d+\]' --protect-regex '\[ruby:[^\]]+\]'
```

La protection fournie ne constitue pas un parseur de tous les langages de balisage : ICU imbriqué, scripts, commandes de plugins et balises atypiques exigent des exclusions ou une règle adaptée. Une expression doit capturer le token complet. Un retour à la ligne est conservé, mais sa bonne position linguistique reste à relire.

## Glossaire de localisation

Pour imposer les noms propres et les libellés d'interface, passer un objet JSON associant une chaîne source **complète et exacte** à sa traduction validée. Ce n'est pas un remplacement de sous-chaînes : cela évite de modifier involontairement le sens des dialogues. Les codes protégés sont aussi vérifiés dans le glossaire.

```powershell
.\translate.ps1 .\examples\game.ja.json -o .\outputs\jeu-localise.json --glossary .\examples\glossary.ja-en.json
```

L'exemple fourni fixe notamment `はじめから` à `New Game`, `つづきから` à `Continue` et les rôles des personnages. Adapter les choix au jeu. Le glossaire prend priorité sur le cache et le modèle, uniquement pour les champs sélectionnés. Le stocker en dehors du dossier de JSON à traduire.

## Reprise et sorties existantes

Les traductions réussies sont enregistrées immédiatement dans `.translation-cache.sqlite3`. Le cache dépend du texte, du digest du modèle, des langues, du découpage et des règles de protection. Il reste local et peut contenir le texte traduit du jeu.

Relancer la commande reprend les traductions déjà obtenues. Si un dossier contient des sorties d'une exécution précédente, ajouter `--overwrite` : chaque sortie préexistante est sauvegardée sous un nom `.bak-...` avant remplacement. **Le fichier source n'est jamais une destination autorisée.**

```powershell
.\translate.ps1 .\data -o .\data-en --overwrite --report .\rapport-nouveau.json
```

Le rapport doit être un nouveau fichier. Le mode normal refuse les sorties existantes. Garder la base de cache pour reprendre ; choisir `--cache .\autre-cache.sqlite3` pour forcer un essai indépendant.

## Modèle et réglages GPU

Pour refaire l'installation ou préparer une autre machine Windows équipée de Python et Winget :

```powershell
.\setup-ollama.ps1
```

Ce script installe Ollama s'il manque, télécharge `translategemma:12b`, vérifié par Ollama, et crée le profil défini dans `Modelfile` :

```text
FROM translategemma:12b
PARAMETER temperature 0
PARAMETER num_ctx 2048
PARAMETER num_predict 768
```

Les deux noms partagent les mêmes poids : le profil n'ajoute pas un second téléchargement de 8,1 Go. Aucune variable d'environnement utilisateur/système n'est modifiée. Le lanceur réutilise le serveur Ollama existant ; s'il doit le démarrer, il le limite à l'interface locale, un modèle chargé et une requête parallèle. Le traducteur lui-même envoie toujours ses requêtes séquentiellement et applique ses paramètres à chaque requête.

Le modèle reste chargé cinq minutes après utilisation, puis Ollama peut le décharger. Pour le libérer immédiatement :

```powershell
ollama stop ja-en-game:12b
```

Sur cette machine, `ollama.exe` est installé dans `%LOCALAPPDATA%\Programs\Ollama`. Ouvrir un nouveau terminal pour bénéficier du PATH ajouté par l'installateur.

Ollama choisit automatiquement la répartition GPU/CPU en fonction de la VRAM libre. Vérifier avec `ollama ps`. Avec d'autres applications utilisant le GPU, une partie peut être déportée en RAM et ralentir l'inférence. Le script ne ferme aucune autre application.

## Limites de traduction

TranslateGemma est spécialisé en traduction. Le prompt suit le format de sa fiche Ollama. La documentation Google indique un contexte d'entrée de 2 000 tokens ; le script utilise des segments courts, au maximum 300 caractères et un budget UTF-8 conservateur, avec 768 tokens de sortie. `--chunk-chars 150` permet de réduire encore les segments.

Les chaînes sont traduites individuellement, sans historique des scènes. Les longues chaînes sont découpées de préférence aux frontières de phrases. Cela limite la cohérence des pronoms implicites, noms propres et expressions entre dialogues ; une relecture dans le jeu reste nécessaire. La syntaxe et les tokens connus sont contrôlés, **la qualité linguistique et la compatibilité avec un moteur inconnu ne sont pas garanties**.

Pour changer de langue, fournir les noms et codes au modèle. Ajouter `--all-strings` pour une source autre que le japonais :

```powershell
.\translate.ps1 .\jeu.json --target 'French (fr)' -o .\jeu.fr.json
.\translate.ps1 .\english.json --source 'English (en)' --target 'French (fr)' --all-strings -o .\french.json
```

## Tests

```powershell
python -X utf8 -m unittest -v
```

Les tests vérifient les données conservées, les nombres précis, les tokens, les filtres, les encodages, le cache, les réponses tronquées, les sauvegardes et l'absence de sortie partielle. L'exemple `examples/game.ja.json` permet en plus un essai réel sur le modèle.

Sources : [TranslateGemma Google](https://huggingface.co/google/translategemma-12b-it), [modèle Ollama et format du prompt](https://ollama.com/library/translategemma:12b), [API Ollama](https://docs.ollama.com/api/generate), [installation Windows](https://docs.ollama.com/windows).


## Application Android et accès distant

Consulte [le guide Android et Freebox](ANDROID.md). APK signé dans `releases/`, compagnon Windows démarré par `Demarrer-Kotoba-PC.cmd`. Limite mobile : 50 Mo par fichier.
