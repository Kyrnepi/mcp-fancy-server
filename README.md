# Fancy Control MCP Server

**🌐 Language / Langue : [English](#english) | [Français](#français)**

---

<a name="english"></a>
## 🇬🇧 English

HTTP Streamable MCP (Model Context Protocol) server for controlling PowerExchange/Fancy Control devices.

### Features

| Tool | Description |
|------|-------------|
| `freeze_lock` | FREEZE LOCK (BETA) - Activate Pet Training freeze mode (S2Z) - must stay still |
| `warning_buzzer` | Enable/disable the warning buzzer |
| `pet_training` | Pet Training mode (normal, fast, freeze) |
| `sleep_deprivation` | Sleep Deprivation mode |
| `random_mode` | Random mode - random activation |
| `timer` | Timer mode (on/off, t1_up/t1_down, t2_up/t2_down) |
| `beep` | Send a beep (short press equivalent) |
| `shock` | Send a shock with power 1-100% (long press equivalent) |
| `power_control` | Power level control |
| `send_raw_command` | Raw HTTP command for advanced users |

### Architecture

```
MCP Client ──────► Raspberry Pi ──────► Fancy Device
             eth0 (Ethernet)     wlan0 (WiFi)
             Port 8000           Port 80
```

### Quick Start

#### On Raspberry Pi (ARM64) with Docker

```bash
git clone <repository-url>
cd fancy-mcp-server

# Build the image
docker build -t fancy-mcp-server .

# Run the container
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=your-secure-token \
  -e DEVICE_IP=192.168.4.1 \
  -e DEVICE_PORT=80 \
  -e MCP_CONTEXT_DESCRIPTION="My Fancy device" \
  fancy-mcp-server
```

#### With docker-compose

```bash
git clone <repository-url>
cd fancy-mcp-server
cp .env.example .env
# Edit .env with your settings
docker compose up -d
```

See [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) for complete WiFi configuration.

#### Without Docker (Python)

```bash
pip install -r requirements.txt
export MCP_AUTH_TOKEN=your-token
export DEVICE_IP=192.168.4.1
python server.py
```

### Environment Variables

#### Basic Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_AUTH_TOKEN` | Yes | - | MCP authentication token |
| `DEVICE_IP` | Yes | - | Device IP address |
| `DEVICE_PORT` | No | 80 | Device HTTP port |
| `MCP_CONTEXT_DESCRIPTION` | No | - | Prefix added to all descriptions |
| `PORT` | No | 8000 | MCP server port |
| `MCP_SAFETY_MAX_POWER_0_100` | No | - | **Safety**: Maximum power limit (0-100). If set, all power commands (shock, power_control) will be capped at this value |

#### Tool Descriptions (customizable)

Each tool has its own variable to customize its description:

| Variable | Default Description |
|----------|---------------------|
| `TOOL_DESC_FREEZE_LOCK` | FREEZE LOCK (BETA) - Lock or unlock the device... |
| `TOOL_DESC_WARNING_BUZZER` | Warning Buzzer - Enable or disable the warning buzzer... |
| `TOOL_DESC_PET_TRAINING` | Pet Training Mode - Enable or disable pet training... |
| `TOOL_DESC_SLEEP_DEPRIVATION` | Sleep Deprivation Mode - Enable or disable... |
| `TOOL_DESC_RANDOM_MODE` | Random Mode - Enable or disable random activation... |
| `TOOL_DESC_TIMER` | Timer Mode - Enable or disable timer mode... |
| `TOOL_DESC_BEEP` | Beep - Send a beep signal to the device... |
| `TOOL_DESC_SHOCK` | Shock - Send a shock signal with specified power... |
| `TOOL_DESC_POWER_CONTROL` | Power Control - Adjust the device power level |
| `TOOL_DESC_SEND_RAW_COMMAND` | Send a raw HTTP command to the device... |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | Main MCP endpoint (JSON-RPC) |
| `/health` | GET | Health check |
| `/` | GET | Server info |

### Authentication

The server accepts the token with or without "Bearer" prefix:

```bash
# With Bearer
-H "Authorization: Bearer your-token"

# Without Bearer
-H "Authorization: your-token"
```

### Usage Examples

#### Health Check
```bash
curl http://192.168.1.100:8000/health
```

#### List Tools
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

#### Send a Beep
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "beep", "arguments": {}}}'
```

#### Shock at 50% Power
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "shock", "arguments": {"power": 50}}}'
```

#### Enable Freeze Lock
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "freeze_lock", "arguments": {"action": "on"}}}'
```

#### Enable Timer Mode
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "timer", "arguments": {"action": "on"}}}'
```

#### Increase Timer 1
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: your-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "timer", "arguments": {"action": "t1_up"}}}'
```

### Device Endpoints

| Function | Endpoint |
|----------|----------|
| Freeze Lock ON | `/mode/S2Z` |
| Freeze Lock OFF | `/mode/0` |
| Buzzer ON | `/S1/1` |
| Buzzer OFF | `/S1/0` |
| Pet Training (normal) | `/mode/S2` |
| Pet Training (fast) | `/mode/S2F` |
| Pet Training (freeze) | `/mode/S2Z` |
| Sleep Deprivation | `/mode/S4` |
| Random | `/mode/RN` |
| Timer Mode | `/mode/TM` |
| Timer 1 + | `/T1/+` |
| Timer 1 - | `/T1/-` |
| Timer 2 + | `/T2/+` |
| Timer 2 - | `/T2/-` |
| Mode OFF | `/mode/0` |
| Beep | `/B1/1` |
| Shock | `/Z1/1` |
| Power + | `/PW/+` |
| Power - | `/PW/-` |

### Docker

#### Build
```bash
docker build -t fancy-mcp-server .
```

#### Run (minimal config)
```bash
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=your-token \
  -e DEVICE_IP=192.168.4.1 \
  fancy-mcp-server
```

#### Run (full config with custom descriptions)
```bash
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=your-token \
  -e DEVICE_IP=192.168.4.1 \
  -e DEVICE_PORT=80 \
  -e MCP_CONTEXT_DESCRIPTION="My Device" \
  -e MCP_SAFETY_MAX_POWER_0_100=50 \
  -e TOOL_DESC_FREEZE_LOCK="Device lock" \
  -e TOOL_DESC_WARNING_BUZZER="Warning buzzer" \
  -e TOOL_DESC_PET_TRAINING="Training mode" \
  -e TOOL_DESC_SLEEP_DEPRIVATION="Sleep deprivation mode" \
  -e TOOL_DESC_RANDOM_MODE="Random mode" \
  -e TOOL_DESC_TIMER="Timer" \
  -e TOOL_DESC_BEEP="Send a beep" \
  -e TOOL_DESC_SHOCK="Send a shock" \
  -e TOOL_DESC_POWER_CONTROL="Power control" \
  -e TOOL_DESC_SEND_RAW_COMMAND="Raw command" \
  fancy-mcp-server
```

> **Safety Note**: The `MCP_SAFETY_MAX_POWER_0_100` variable limits the maximum power. In the example above, even if a shock is requested at 100%, it will be limited to 50%.

#### Stop / Remove
```bash
docker stop fancy-mcp-server
docker rm fancy-mcp-server
```

#### Logs
```bash
docker logs -f fancy-mcp-server
```

#### With docker-compose
```bash
docker compose build
docker compose up -d
docker compose logs -f
```

### MCP Compliance

- Protocol Version: 2024-11-05
- Transport: HTTP Streamable
- Format: JSON-RPC 2.0
- Methods: initialize, tools/list, tools/call, resources/list, resources/read, prompts/list, prompts/get, ping

---

<a name="français"></a>
## 🇫🇷 Français

Serveur MCP (Model Context Protocol) HTTP Streamable pour contrôler les appareils PowerExchange/Fancy Control.

### Fonctionnalités

| Outil | Description |
|-------|-------------|
| `freeze_lock` | FREEZE LOCK (BETA) - Active le mode Pet Training freeze (S2Z) - doit rester immobile |
| `warning_buzzer` | Active/désactive le buzzer d'avertissement |
| `pet_training` | Mode Pet Training (normal, fast, freeze) |
| `sleep_deprivation` | Mode Sleep Deprivation |
| `random_mode` | Mode Random - activation aléatoire |
| `timer` | Mode Timer (on/off, t1_up/t1_down, t2_up/t2_down) |
| `beep` | Envoie un bip (équivalent appui court) |
| `shock` | Envoie un shock avec puissance 1-100% (équivalent appui long) |
| `power_control` | Contrôle du niveau de puissance |
| `send_raw_command` | Commande HTTP brute pour utilisateurs avancés |

### Architecture

```
Client MCP ──────► Raspberry Pi ──────► Device Fancy
             eth0 (Ethernet)     wlan0 (WiFi)
             Port 8000           Port 80
```

### Installation rapide

#### Sur Raspberry Pi (ARM64) avec Docker

```bash
git clone <repository-url>
cd fancy-mcp-server

# Build de l'image
docker build -t fancy-mcp-server .

# Lancer le container
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=votre-token-securise \
  -e DEVICE_IP=192.168.4.1 \
  -e DEVICE_PORT=80 \
  -e MCP_CONTEXT_DESCRIPTION="Mon device Fancy" \
  fancy-mcp-server
```

#### Avec docker-compose

```bash
git clone <repository-url>
cd fancy-mcp-server
cp .env.example .env
# Éditer .env avec vos paramètres
docker compose up -d
```

Voir [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) pour la configuration WiFi complète.

#### Sans Docker (Python)

```bash
pip install -r requirements.txt
export MCP_AUTH_TOKEN=votre-token
export DEVICE_IP=192.168.4.1
python server.py
```

### Variables d'environnement

#### Configuration de base

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `MCP_AUTH_TOKEN` | Oui | - | Token d'authentification MCP |
| `DEVICE_IP` | Oui | - | Adresse IP du device |
| `DEVICE_PORT` | Non | 80 | Port HTTP du device |
| `MCP_CONTEXT_DESCRIPTION` | Non | - | Préfixe ajouté à toutes les descriptions |
| `PORT` | Non | 8000 | Port du serveur MCP |
| `MCP_SAFETY_MAX_POWER_0_100` | Non | - | **Sécurité** : Limite maximale de puissance (0-100). Si définie, toutes les commandes de puissance (shock, power_control) seront plafonnées à cette valeur |

#### Descriptions des outils (personnalisables)

Chaque outil a sa propre variable pour personnaliser sa description :

| Variable | Description par défaut |
|----------|------------------------|
| `TOOL_DESC_FREEZE_LOCK` | FREEZE LOCK (BETA) - Lock or unlock the device... |
| `TOOL_DESC_WARNING_BUZZER` | Warning Buzzer - Enable or disable the warning buzzer... |
| `TOOL_DESC_PET_TRAINING` | Pet Training Mode - Enable or disable pet training... |
| `TOOL_DESC_SLEEP_DEPRIVATION` | Sleep Deprivation Mode - Enable or disable... |
| `TOOL_DESC_RANDOM_MODE` | Random Mode - Enable or disable random activation... |
| `TOOL_DESC_TIMER` | Timer Mode - Enable or disable timer mode... |
| `TOOL_DESC_BEEP` | Beep - Send a beep signal to the device... |
| `TOOL_DESC_SHOCK` | Shock - Send a shock signal with specified power... |
| `TOOL_DESC_POWER_CONTROL` | Power Control - Adjust the device power level |
| `TOOL_DESC_SEND_RAW_COMMAND` | Send a raw HTTP command to the device... |

### Endpoints API

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/mcp` | POST | Endpoint MCP principal (JSON-RPC) |
| `/health` | GET | Health check |
| `/` | GET | Info serveur |

### Authentification

Le serveur accepte le token avec ou sans préfixe "Bearer" :

```bash
# Avec Bearer
-H "Authorization: Bearer votre-token"

# Sans Bearer
-H "Authorization: votre-token"
```

### Exemples d'utilisation

#### Health Check
```bash
curl http://192.168.1.100:8000/health
```

#### Liste des outils
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

#### Envoyer un Beep
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "beep", "arguments": {}}}'
```

#### Shock à 50% de puissance
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "shock", "arguments": {"power": 50}}}'
```

#### Activer Freeze Lock
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "freeze_lock", "arguments": {"action": "on"}}}'
```

#### Activer le mode Timer
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "timer", "arguments": {"action": "on"}}}'
```

#### Augmenter Timer 1
```bash
curl -X POST http://192.168.1.100:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "timer", "arguments": {"action": "t1_up"}}}'
```

### Endpoints du Device

| Fonction | Endpoint |
|----------|----------|
| Freeze Lock ON | `/mode/S2Z` |
| Freeze Lock OFF | `/mode/0` |
| Buzzer ON | `/S1/1` |
| Buzzer OFF | `/S1/0` |
| Pet Training (normal) | `/mode/S2` |
| Pet Training (fast) | `/mode/S2F` |
| Pet Training (freeze) | `/mode/S2Z` |
| Sleep Deprivation | `/mode/S4` |
| Random | `/mode/RN` |
| Timer Mode | `/mode/TM` |
| Timer 1 + | `/T1/+` |
| Timer 1 - | `/T1/-` |
| Timer 2 + | `/T2/+` |
| Timer 2 - | `/T2/-` |
| Mode OFF | `/mode/0` |
| Beep | `/B1/1` |
| Shock | `/Z1/1` |
| Power + | `/PW/+` |
| Power - | `/PW/-` |

### Docker

#### Build
```bash
docker build -t fancy-mcp-server .
```

#### Lancer (config minimale)
```bash
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=votre-token \
  -e DEVICE_IP=192.168.4.1 \
  fancy-mcp-server
```

#### Lancer (config complète avec descriptions personnalisées)
```bash
docker run -d \
  --name fancy-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MCP_AUTH_TOKEN=votre-token \
  -e DEVICE_IP=192.168.4.1 \
  -e DEVICE_PORT=80 \
  -e MCP_CONTEXT_DESCRIPTION="Mon Device" \
  -e MCP_SAFETY_MAX_POWER_0_100=50 \
  -e TOOL_DESC_FREEZE_LOCK="Verrouillage du device" \
  -e TOOL_DESC_WARNING_BUZZER="Buzzer d'avertissement" \
  -e TOOL_DESC_PET_TRAINING="Mode dressage" \
  -e TOOL_DESC_SLEEP_DEPRIVATION="Mode privation de sommeil" \
  -e TOOL_DESC_RANDOM_MODE="Mode aléatoire" \
  -e TOOL_DESC_TIMER="Minuterie" \
  -e TOOL_DESC_BEEP="Émettre un bip" \
  -e TOOL_DESC_SHOCK="Envoyer une décharge" \
  -e TOOL_DESC_POWER_CONTROL="Contrôle de puissance" \
  -e TOOL_DESC_SEND_RAW_COMMAND="Commande brute" \
  fancy-mcp-server
```

> **Note sécurité** : La variable `MCP_SAFETY_MAX_POWER_0_100` permet de limiter la puissance maximale. Dans l'exemple ci-dessus, même si un shock est demandé à 100%, il sera limité à 50%.

#### Arrêter / Supprimer
```bash
docker stop fancy-mcp-server
docker rm fancy-mcp-server
```

#### Logs
```bash
docker logs -f fancy-mcp-server
```

#### Avec docker-compose
```bash
docker compose build
docker compose up -d
docker compose logs -f
```

### Conformité MCP

- Protocol Version: 2024-11-05
- Transport: HTTP Streamable
- Format: JSON-RPC 2.0
- Méthodes: initialize, tools/list, tools/call, resources/list, resources/read, prompts/list, prompts/get, ping

---

## License

MIT License
