# Guide de Configuration Raspberry Pi

Ce guide explique comment configurer un Raspberry Pi pour héberger le serveur MCP Fancy Control avec une connexion WiFi dédiée au device.

## Architecture réseau

```
┌─────────────────┐                    ┌─────────────────┐
│  Client MCP     │                    │  Device FANCY   │
│  (Internet)     │                    │  (192.168.4.1)  │
└────────┬────────┘                    └────────▲────────┘
         │                                      │
         │ Ethernet (eth0)                      │ WiFi (wlan0)
         │                                      │ SSID: FANCY-AP
         ▼                                      │
┌─────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI                              │
│                                                              │
│  eth0: DHCP (accès SSH + réception ordres MCP)              │
│  wlan0: 192.168.4.96 (connexion au device FANCY-AP)         │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Docker Container: fancy-mcp-server                  │    │
│  │  Port 8000 - Reçoit sur eth0, envoie sur wlan0      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Prérequis

- Raspberry Pi 4 ou 5 (ARM64)
- Raspberry Pi OS (64-bit) installé
- Accès SSH fonctionnel via Ethernet
- Docker et Docker Compose installés

## Étape 1 : Configuration WiFi (wlan0)

### 1.1 Créer le fichier de configuration réseau

```bash
sudo nano /etc/network/interfaces.d/wlan0
```

Ajouter le contenu suivant :

```
auto wlan0
iface wlan0 inet static
    address 192.168.4.96
    netmask 255.255.255.0
    gateway 192.168.4.1
    wpa-ssid "FANCY-AP"
    wpa-psk "12345678"
```

### 1.2 Alternative avec wpa_supplicant

Créer/éditer le fichier wpa_supplicant :

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

Ajouter :

```
country=FR
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="FANCY-AP"
    psk="12345678"
    key_mgmt=WPA-PSK
    priority=1
}
```

### 1.3 Configurer l'IP statique via dhcpcd

```bash
sudo nano /etc/dhcpcd.conf
```

Ajouter à la fin :

```
interface wlan0
static ip_address=192.168.4.96/24
static routers=192.168.4.1
static domain_name_servers=192.168.4.1 8.8.8.8
```

### 1.4 Redémarrer les services réseau

```bash
sudo systemctl restart dhcpcd
sudo systemctl restart wpa_supplicant
```

### 1.5 Vérifier la connexion

```bash
# Vérifier les interfaces
ip addr show wlan0

# Tester la connexion au device
ping 192.168.4.1
```

## Étape 2 : Installation de Docker (si pas déjà installé)

```bash
# Installer Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER

# Installer Docker Compose
sudo apt-get install docker-compose-plugin

# Redémarrer pour appliquer les changements
sudo reboot
```

## Étape 3 : Déploiement du serveur MCP

### 3.1 Cloner le repository

```bash
cd ~
git clone <repository-url>
cd fancy-mcp-server
```

### 3.2 Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env
```

Modifier avec vos valeurs :

```env
MCP_AUTH_TOKEN=votre-token-securise
DEVICE_IP=192.168.4.1
DEVICE_PORT=80
MCP_CONTEXT_DESCRIPTION=Fancy Control Device
PORT=8000
```

### 3.3 Construire et démarrer le container

```bash
# Construire l'image pour ARM64
docker compose build

# Démarrer le serveur
docker compose up -d

# Vérifier les logs
docker compose logs -f
```

### 3.4 Vérifier le fonctionnement

```bash
# Test health check
curl http://localhost:8000/health

# Test depuis le réseau externe (via eth0)
curl http://<IP_ETHERNET_PI>:8000/health
```

## Étape 4 : Configuration du routage (optionnel)

Si le container Docker n'arrive pas à joindre le device sur wlan0, utilisez le mode `host` :

```yaml
# Dans docker-compose.yml, décommenter :
network_mode: host
```

Ou configurez le routage manuellement :

```bash
# Permettre le forwarding IP
sudo sysctl -w net.ipv4.ip_forward=1

# Rendre permanent
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
```

## Étape 5 : Démarrage automatique

Le container est configuré avec `restart: unless-stopped`, il redémarrera automatiquement après un reboot.

Pour vérifier :

```bash
# Après reboot
docker ps
```

## Dépannage

### Le WiFi ne se connecte pas

```bash
# Vérifier le statut
sudo wpa_cli status

# Scanner les réseaux
sudo iwlist wlan0 scan | grep ESSID

# Redémarrer wpa_supplicant
sudo systemctl restart wpa_supplicant
```

### Le container ne peut pas joindre le device

```bash
# Vérifier la route
ip route show

# Ajouter une route si nécessaire
sudo ip route add 192.168.4.0/24 dev wlan0

# Tester depuis le Pi (hors container)
curl http://192.168.4.1/health
```

### Logs du serveur MCP

```bash
# Voir les logs en temps réel
docker compose logs -f fancy-mcp-server

# Voir les dernières 100 lignes
docker compose logs --tail=100 fancy-mcp-server
```

## Commandes utiles

```bash
# Redémarrer le serveur
docker compose restart

# Arrêter le serveur
docker compose down

# Reconstruire après modification
docker compose build --no-cache
docker compose up -d

# Voir l'état du container
docker compose ps
```

## Test du serveur MCP

Depuis n'importe quel client sur le réseau Ethernet :

```bash
# Health check
curl http://<IP_ETHERNET_PI>:8000/health

# Liste des outils
curl -X POST http://<IP_ETHERNET_PI>:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Envoyer un beep
curl -X POST http://<IP_ETHERNET_PI>:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: votre-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "beep", "arguments": {}}}'
```
