# Black Cat

Black Cat is a simple online **Hearts** clone inspired by the old Windows card game called “fekete macska”. I used to play it with friends during LAN parties between game sessions, and this project brings that same quick, social card game vibe to the web.

## Features
- Online Hearts for 4 players
- Invite-link lobby
- Optional bot players
- Simple black/red card UI

## Tech
- FastAPI + WebSockets
- Vanilla HTML/CSS/JS
- Container-ready (Podman/Docker)

## Run locally
```
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 9200
```

Visit: `http://localhost:9200`

## Run in a container
```
podman build -t blackcat-hearts .
podman run -p 9200:9200 blackcat-hearts
```

## Deploy with Caddy
```
subdomain.domain.com {
  reverse_proxy 127.0.0.1:9200
}
```
