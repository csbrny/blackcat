const state = {
  ws: null,
  roomId: null,
  playerId: null,
  selectedPass: new Set(),
  currentState: null,
};

const el = (id) => document.getElementById(id);

const suitSymbols = {
  C: "♣️",
  D: "♦️",
  H: "♥️",
  S: "♠️",
};

const rankLabels = {
  T: "10",
  J: "J",
  Q: "Q",
  K: "K",
  A: "A",
};

function formatCard(card) {
  const rank = card[0];
  const suit = card[1];
  const rankLabel = rankLabels[rank] || rank;
  const suitLabel = suitSymbols[suit] || suit;
  return `${suitLabel}${rankLabel}`;
}

const cardIsRed = (card) => card.endsWith("H") || card.endsWith("D");

function storageName() {
  return window.localStorage.getItem("bc_name") || "";
}

function saveName(name) {
  window.localStorage.setItem("bc_name", name);
}

function getName() {
  let name = storageName();
  if (!name) {
    name = window.prompt("Name?") || "Player";
    saveName(name);
  }
  return name;
}

function showHome() {
  el("screen-home").classList.remove("hidden");
  el("screen-room").classList.add("hidden");
}

function showRoom() {
  el("screen-home").classList.add("hidden");
  el("screen-room").classList.remove("hidden");
}

async function createRoom() {
  const name = el("name-input").value.trim() || "Player";
  saveName(name);
  const res = await fetch("/api/rooms", { method: "POST" });
  const data = await res.json();
  window.location.href = `/room/${data.room_id}`;
}

function joinRoom() {
  const name = el("name-input").value.trim() || "Player";
  saveName(name);
  const roomId = el("join-room-id").value.trim().toUpperCase();
  if (!roomId) return;
  window.location.href = `/room/${roomId}`;
}

function connect(roomId) {
  const name = getName();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${roomId}?name=${encodeURIComponent(name)}`);
  state.ws = ws;
  state.roomId = roomId;

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "state") {
      state.currentState = msg.state;
      state.playerId = msg.state.your_id;
      renderState(msg.state);
    }
  };

  ws.onclose = () => {
    alert("Disconnected from room.");
    window.location.href = "/";
  };
}

function send(action) {
  if (!state.ws) return;
  state.ws.send(JSON.stringify(action));
}

function renderPlayers(players) {
  const container = el("players");
  container.innerHTML = "";
  players.forEach((p) => {
    const div = document.createElement("div");
    div.className = "player";
    const title = document.createElement("strong");
    title.textContent = p.name + (p.is_bot ? " (bot)" : "");
    const score = document.createElement("span");
    score.textContent = `Score: ${p.score}`;
    div.appendChild(title);
    div.appendChild(score);
    container.appendChild(div);
  });
}

function seatOrder(players, yourId) {
  if (!players.length) return [];
  const idx = players.findIndex((p) => p.id === yourId);
  if (idx === -1) return players;
  const order = [];
  for (let i = 0; i < players.length; i += 1) {
    order.push(players[(idx + i) % players.length]);
  }
  return order;
}

function renderScoreboard(players, roundPoints) {
  const container = el("scoreboard-list");
  if (!container) return;
  container.innerHTML = "";
  const sorted = [...players].sort((a, b) => a.score - b.score);
  sorted.forEach((p) => {
    const chip = document.createElement("div");
    chip.className = "score-chip";
    chip.textContent = `${p.name}: ${p.score}`;
    container.appendChild(chip);
  });

  const roundEl = el("round-points");
  if (roundEl) {
    const entries = sorted.map((p) => `${p.name} ${roundPoints[p.id] ?? 0}`);
    roundEl.textContent = entries.length ? `Round points: ${entries.join(" | ")}` : "";
  }
}

function renderTable(data) {
  const seats = {
    south: el("seat-south"),
    west: el("seat-west"),
    north: el("seat-north"),
    east: el("seat-east"),
  };

  const order = seatOrder(data.players, data.your_id);
  const placement = ["south", "west", "north", "east"];
  const trickMap = new Map(data.trick.map((play) => [play.player_id, play.card]));
  const nameMap = new Map(data.players.map((p) => [p.id, p.name]));

  placement.forEach((pos, idx) => {
    const seat = seats[pos];
    seat.classList.remove("turn");
    const player = order[idx];
    if (!player) {
      seat.innerHTML = "<div class=\"name\">Empty</div>";
      return;
    }

    const isYou = player.id === data.your_id;
    if (player.id === data.current_turn) {
      seat.classList.add("turn");
    }

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = `${player.name}${isYou ? " (you)" : ""}`;

    const card = document.createElement("div");
    card.className = "card";
    const played = trickMap.get(player.id);
    if (played) {
      card.textContent = formatCard(played);
      if (cardIsRed(played)) card.classList.add("red");
    } else {
      card.textContent = "--";
    }

    seat.innerHTML = "";
    seat.appendChild(name);
    seat.appendChild(card);
  });

  const center = el("table-center");
  if (center) {
    if (data.phase === "game_over") {
      const winner = nameMap.get(data.winner_id) || "Player";
      center.textContent = `End game: ${winner} wins 🎉`;
    } else if (data.phase === "round_end") {
      center.textContent = "Round over";
    } else if (data.phase === "playing" && !data.active_trick) {
      const currentName = nameMap.get(data.current_turn) || "player";
      center.textContent = data.current_turn === data.your_id ? "Your lead" : `Waiting for ${currentName}`;
    } else {
      center.textContent = "Trick";
    }
  }
}

function renderHand(hand, legalMoves, pendingPass) {
  const container = el("hand");
  container.innerHTML = "";

  hand.forEach((card) => {
    const div = document.createElement("button");
    div.className = "card";
    if (cardIsRed(card)) div.classList.add("red");
    if (legalMoves.includes(card)) div.classList.add("playable");
    if (state.selectedPass.has(card)) div.classList.add("selected");
    div.textContent = formatCard(card);

    div.onclick = () => {
      if (pendingPass) {
        if (state.selectedPass.has(card)) {
          state.selectedPass.delete(card);
        } else if (state.selectedPass.size < 3) {
          state.selectedPass.add(card);
        }
        renderHand(hand, legalMoves, pendingPass);
        updatePassButton();
        return;
      }
      if (legalMoves.includes(card)) {
        send({ type: "play_card", card });
      }
    };

    container.appendChild(div);
  });
}

function updatePassButton() {
  const btn = el("submit-pass");
  btn.disabled = state.selectedPass.size !== 3;
}

function renderState(data) {
  el("room-id").textContent = data.room_id;
  const phaseLabel = data.phase ? data.phase.replace("_", " ") : "";
  el("room-phase").textContent = phaseLabel;
  el("invite-link").textContent = `${window.location.origin}/room/${data.room_id}`;

  renderPlayers(data.players);
  renderScoreboard(data.players, data.round_points || {});

  const isLobby = data.phase === "lobby";
  el("lobby").classList.toggle("hidden", !isLobby);
  el("game").classList.toggle("hidden", isLobby);

  el("add-bot").disabled = !data.can_start || data.players.length >= data.max_players || data.phase !== "lobby";
  el("start-game").disabled = !data.can_start || data.players.length < data.max_players || data.phase !== "lobby";

  if (!isLobby) {
    el("pass-dir").textContent = data.pass_dir;
    const playerMap = new Map(data.players.map((p) => [p.id, p.name]));
    el("current-turn").textContent = playerMap.get(data.current_turn) || "-";

    renderTable(data);

    const pendingPass = data.phase === "passing" && data.pending_pass;
    if (!pendingPass) state.selectedPass.clear();
    renderHand(data.hand, data.legal_moves || [], pendingPass);

    el("pass-controls").classList.toggle("hidden", !pendingPass);
    updatePassButton();

    const showRoundControls = data.phase === "round_end" && data.can_start;
    el("round-controls").classList.toggle("hidden", !showRoundControls);
  }
}

function init() {
  el("create-room").addEventListener("click", createRoom);
  el("join-room").addEventListener("click", joinRoom);
  el("add-bot").addEventListener("click", () => send({ type: "add_bot" }));
  el("start-game").addEventListener("click", () => send({ type: "start_game" }));
  el("submit-pass").addEventListener("click", () => {
    if (state.selectedPass.size === 3) {
      send({ type: "pass_cards", cards: Array.from(state.selectedPass) });
    }
  });
  el("start-round").addEventListener("click", () => send({ type: "start_round" }));
  el("copy-invite").addEventListener("click", async () => {
    const link = el("invite-link").textContent.trim();
    if (!link) return;
    const button = el("copy-invite");
    const feedback = el("copy-feedback");
    try {
      await navigator.clipboard.writeText(link);
      if (feedback) feedback.textContent = "Copied!";
      if (button) button.classList.add("copied");
    } catch (err) {
      window.prompt("Copy invite link:", link);
      if (feedback) feedback.textContent = "Copy manually";
    }
    if (button) {
      setTimeout(() => button.classList.remove("copied"), 1200);
    }
    if (feedback) {
      setTimeout(() => (feedback.textContent = ""), 1600);
    }
  });

  const path = window.location.pathname;
  if (path.startsWith("/room/")) {
    const roomId = path.split("/room/")[1].toUpperCase();
    showRoom();
    connect(roomId);
  } else {
    showHome();
    el("name-input").value = storageName();
  }
}

init();
