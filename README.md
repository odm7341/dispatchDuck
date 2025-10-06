# Dispatchwrapparr - Simple tsp wrapper for Dispatcharr

<p align="center">
  <img src="https://github.com/user-attachments/assets/eb65168b-e24f-4e0c-b17b-7d72021d1d15" height="250" alt="Dispatchwrapparr Logo" />
</p>

## 🤝 What does Dispatchwrapparr do?

✅ **Simple & Lightweight** — Uses tsduck's tsp command directly for reliable MPEG-TS streaming\
✅ **User-Agent Support** — Configurable User-Agent headers for stream access\
✅ **Easy Installation** — Simple plugin-based installation and management

----

## 🚀 Installation

Dispatchwrapparr can be easily installed via the Dispatchwrapparr Plugin.

1. Download the latest [Dispatchwrapparr Plugin](https://github.com/jordandalley/dispatchwrapparr/releases/latest) zip file
2. In Dispatcharr, navigate to 'Settings' > 'Plugins'
3. Click the 'Import Plugin' button and select the Dispatchwrapparr Plugin zip file you just downloaded
4. Select 'Enable Now', and then 'Enable'
5. Once the plugin is loaded, click 'Run' inside the 'Install Dispatchwrapparr' section
<img width="489" height="278" alt="image" src="https://github.com/user-attachments/assets/0b00bdd6-7ad9-428c-b2b0-66e62279e747" />

6. An alert box should come up to confirm installation
<img width="350" height="87" alt="image" src="https://github.com/user-attachments/assets/082e4a58-6d1e-4945-bcae-168692a667be" />

7. Click the refresh icon <img width="29" height="29" alt="image" src="https://github.com/user-attachments/assets/0945ad01-9af6-49bf-80e6-ff9607bdc501" /> to display all available settings

## ➡️ Create a Dispatchwrapparr stream profile

Dispatchwrapparr profiles can be created through the plugin interface.

1. Navigate to 'Settings' > 'Plugins' in Dispatcharr
2. Find the Dispatchwrapparr plugin and enter a 'Profile Name'
3. Click 'Run' next to 'Create Stream Profile'
4. Refresh your browser, then apply the profile to any streams you want
5. Select 'dispatchwrapparr' as your preferred profile on streams!

Alternatively, you can create profiles manually by adding them under 'Settings' > 'Stream Profiles' in Dispatcharr. Dispatchwrapparr is usually installed under `/data/dispatchwrapparr/dispatchwrapparr.py`.

----

## ⚙️ CLI Arguments

| Argument        | Type     | Example Values                                            | Description                                                                                                                                                                                  |
| :---            | :---     | :---                                                      | :---                                                                                                                                                                                         |
| -i              | Required | `{streamUrl}`                                             | Input stream URL from Dispatcharr.                                                                                                                                                           |
| -ua             | Required | `{userAgent}`                                             | Input user-agent header from Dispatcharr.                                                                                                                                                    |
| -v, --version   | Optional |                                                           | Display Dispatchwrapparr version information.                                                                                                                                                |

Example: `dispatchwrapparr.py -i {streamUrl} -ua {userAgent}`

----

## 🛠️ Requirements

- **tsduck** must be installed and available in your system PATH
- Works with any HTTP/HTTPS stream URL that tsp can handle
- Compatible with Dispatcharr for stream processing

## ⚖️ License

This project is licensed under the [MIT License](LICENSE).