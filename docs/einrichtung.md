# Einrichtung: OpenGothic mit KI-Spielleiter

Diese Anleitung richtet das Projekt auf einem eigenen Mac ein: das Spiel, den Spielleiter, den Inspektor im Browser
und, wenn du willst, die Stimmen. Sie ist für einen Mac mit Apple-Chip (M1 oder neuer) geschrieben, weil die
Stimmen nur dort laufen.

## Bevor du anfängst

- Du brauchst **deine eigene Kopie von Gothic II Gold** (Steam). OpenGothic liefert keine Spieldateien mit.
- **Die Stimmen erzeugst du selbst**, aus deiner eigenen Spielinstallation. Geklonte Stimmen, Stimmdateien und
  Stimmmodelle werden nicht weitergegeben und gehören in kein Repository. Sie bleiben privat auf deinem Rechner.
- Alles, was die Stimmen und die zitierten Spieltexte betrifft, landet in `python/dm_runtime/`. Dieser Ordner wird
  von Git ignoriert und soll es bleiben.

## 1. Werkzeuge installieren

Mit [Homebrew](https://brew.sh):

```sh
brew install cmake glslang python@3.11 git
```

`glslang` stellt `glslangValidator` bereit, den der Build für die Shader braucht.

## 2. Code holen und bauen

```sh
git clone --recurse-submodules -b python-repl https://github.com/theGreatHerrLebert/OpenGothic.git
cd OpenGothic
cmake -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --target Gothic2Notr -j 8
```

Der erste Build dauert eine Weile. Warnungen gelten als Fehler: Wenn der Build abbricht, steht die Ursache in der
ersten Zeile mit `error:`.

## 3. Spieldateien besorgen

Die Mac-Version von Steam installiert Gothic II nicht. Lade die Windows-Dateien mit
[DepotDownloader](https://github.com/SteamRE/DepotDownloader) und deinem eigenen Steam-Konto herunter, mit
`-app 39510` und `-language german`, zum Beispiel nach `~/games/gothicii-gold-de`.

Blockiert macOS das Programm beim ersten Start, erlaube es unter **Systemeinstellungen → Datenschutz & Sicherheit**.

## 4. Das Spiel starten

Immer aus dem Projektordner, damit das Spiel den Ordner `python/` findet:

```sh
OPENGOTHIC_PY_BRIDGE=1 build/opengothic/Gothic2Notr -g ~/games/gothicii-gold-de -devmode
```

`OPENGOTHIC_PY_BRIDGE=1` erlaubt es Werkzeugen außerhalb des Spiels, mit dem laufenden Spiel zu sprechen.
`-devmode` schaltet die Entwicklerkonsole frei (F2).

Den Spielleiter startest du nach dem Laden eines Spielstands, in einem zweiten Terminal:

```sh
scripts/pyeval 'import dm; dm.start()'
```

**Alt+O** blendet die kleine Anzeige oben links ein und aus, die zeigt, woran der Spielleiter gerade arbeitet.

## 5. Der Inspektor im Browser

```sh
python3 python/dm/inspector_server.py
```

Damit der Inspektor ohne Internet läuft, einmal die beiden Graph-Bibliotheken holen (sie werden vor dem Speichern
geprüft):

```sh
python3 python/dm/fetch_vendor.py
```

Dann <http://127.0.0.1:8765> öffnen. Oben rechts stellst du mit **EN | DE** die Sprache um, der Browser merkt sich die
Wahl. Der Inspektor ist nur auf deinem eigenen Rechner erreichbar.

- **Inspektor:** die Referenzgeschichte „Der Fall Tilo“, Zeile für Zeile, mit Ablaufgraph.
- **Figuren:** die Charakterbögen mit Belegzitaten aus dem Spiel. Die Zitate schneidet ein Skript aus deiner eigenen
  Installation, einmal ausführen genügt:

  ```sh
  python3 python/dm/make_quotes.py build ~/games/gothicii-gold-de
  ```
- **Geschichtenprobe:** Geschichten blind bewerten. Die Geschichten selbst liegen in `python/dm_runtime/experiment/`
  und sind nicht im Repository, die Seite ist also zunächst leer.

## 6. Stimmen erzeugen (optional)

Ohne Stimmen läuft alles, die Zeilen erscheinen dann als stumme Untertitel.

Eine eigene Python-Umgebung für das Sprachmodell anlegen:

```sh
python3.11 -m venv python/dm_runtime/tts/venv-mlx
python/dm_runtime/tts/venv-mlx/bin/pip install mlx-audio
```

Referenzstimmen aus deiner Installation ziehen. Jede Nummer ist ein Sprecher des Spiels, 15 ist der Held:

```sh
python3 python/dm/bake_voices.py refs ~/games/gothicii-gold-de 01 03 04 05 06 07 08 09 10 12 13 14 15 16
```

Dann die Zeilen einer Geschichte erzeugen. Die erste Ausführung lädt das Sprachmodell herunter, danach dauert jede
Zeile etwa 7 bis 8 Sekunden. Fortschritt erscheint auch in der Anzeige im Spiel:

```sh
python/dm_runtime/tts/venv-mlx/bin/python python/dm/bake_voices.py bake <graphs.json> "Titel der Geschichte"
```

## 7. Einen KI-Agenten als Spielleiter anbinden (optional)

Der Spielleiter liest das Spiel über einen MCP-Server. Eine Umgebung dafür anlegen:

```sh
python3.11 -m venv python/dm_runtime/mcp
python/dm_runtime/mcp/bin/pip install mcp
```

**Mit Codex** genügt ein Befehl im Projektordner:

```sh
codex mcp add gothic -- "$PWD/python/dm_runtime/mcp/bin/python" -I "$PWD/python/dm/mcp_server.py"
```

**Mit Claude Code** im Projektordner eine Datei `.mcp.json` anlegen, mit deinem eigenen Pfad statt `/PFAD/ZU`:

```json
{
  "mcpServers": {
    "gothic": {
      "command": "/PFAD/ZU/OpenGothic/python/dm_runtime/mcp/bin/python",
      "args": ["-I", "/PFAD/ZU/OpenGothic/python/dm/mcp_server.py"]
    }
  }
}
```

Wie der Spielleiter arbeitet, steht in `docs/director-brief.md` und `docs/quest-design.md`. Hinweise für Agenten, die am
Code arbeiten, stehen in `AGENTS.md`; Codex liest diese Datei von selbst.

## Wenn etwas nicht geht

| Problem | Lösung |
|---|---|
| `scripts/pyeval` meldet `TIMEOUT` | Das Spiel läuft nicht, ist pausiert oder steht in einem Menü. Ins Spiel wechseln. |
| Die Anzeige oben links erscheint nicht | `dm.start()` aufrufen und mit Alt+O prüfen, ob sie nur ausgeblendet ist. |
| Nach einem neuen Build ändert sich nichts | Das Spiel ganz beenden und neu starten. |
| Der Inspektor zeigt „Läuft der Inspektor noch?“ | `inspector_server.py` erneut starten. |
