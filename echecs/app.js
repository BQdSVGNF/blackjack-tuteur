import { Chess } from './vendor/chess.js';

// ---------------------------------------------------------------- config

const ENGINE_URL = 'vendor/stockfish/stockfish-17.1-lite-single-03e3232.js';

// elo: valeur UCI_Elo de Stockfish (null = pleine puissance). time: ms de réflexion par coup.
const BOTS = [
  { name: 'Pion Pressé', label: '1350', elo: 1350, time: 400, e: '🐣', desc: 'Débutant : fait des erreurs, idéal pour apprendre.' },
  { name: 'Cavalier de Club', label: '1700', elo: 1700, time: 500, e: '🐴', desc: 'Joueur de club correct, punit les grosses gaffes.' },
  { name: 'Fou Furieux', label: '2100', elo: 2100, time: 600, e: '🔥', desc: 'Niveau expert, tactiquement dangereux.' },
  { name: 'Maître Tour', label: '2500', elo: 2500, time: 800, e: '🏰', desc: 'Niveau maître international.' },
  { name: 'Grand Maître', label: '2850', elo: 2850, time: 1000, e: '👑', desc: 'Le niveau des meilleurs humains du monde.' },
  { name: 'Super GM', label: '3190', elo: 3190, time: 1000, e: '🧠', desc: 'Au-delà de tout humain. Limite haute du bridage Stockfish.' },
  { name: 'Titan', label: '3200+', elo: null, time: 1000, e: '⚡', top: true, desc: 'Stockfish 17.1 pleine puissance, 1 s par coup.' },
  { name: 'Léviathan', label: '3400+', elo: null, time: 3000, e: '🐉', top: true, desc: 'Stockfish 17.1 pleine puissance, 3 s par coup.' },
  { name: 'Stockfish Max', label: '3500+', elo: null, time: 8000, e: '☠️', top: true, desc: 'Stockfish 17.1 pleine puissance, 8 s par coup. Bonne chance.' },
];

// [minutes, incrément en secondes] ; null = sans pendule
const TCS = [
  { label: 'Sans pendule', tc: null },
  { label: '1 min', tc: [1, 0] },
  { label: '3 | 2', tc: [3, 2] },
  { label: '5 min', tc: [5, 0] },
  { label: '10 min', tc: [10, 0] },
  { label: '15 | 10', tc: [15, 10] },
  { label: '30 min', tc: [30, 0] },
];

const $ = (id) => document.getElementById(id);
const store = {
  get(k, d) { try { const v = localStorage.getItem('echecs.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('echecs.' + k, JSON.stringify(v)); } catch { /* stockage indisponible */ } },
};

const cfg = Object.assign({ mode: 'bot', bot: 6, color: 'w', tc: 0, autoFlip: false }, store.get('cfg', {}));
if (!BOTS[cfg.bot]) cfg.bot = 6;
if (!TCS[cfg.tc]) cfg.tc = 0;
let soundOn = store.get('sound', true);

// ---------------------------------------------------------------- moteur

class Engine {
  constructor() {
    this.resolver = null;
    this.chain = Promise.resolve();
    this.onDepth = null;
    this.failed = false;
    this.ready = new Promise((res, rej) => {
      this._ready = res;
      try {
        this.w = new Worker(ENGINE_URL);
      } catch (err) { this.failed = true; rej(err); return; }
      this.w.onerror = (err) => { this.failed = true; rej(err); };
      this.w.onmessage = (ev) => this.on(String(ev.data));
      this.w.postMessage('uci');
    });
    this.ready.catch(() => {});
  }
  post(s) { this.w.postMessage(s); }
  on(line) {
    if (line === 'uciok') { this.post('setoption name Hash value 64'); this.post('isready'); }
    else if (line === 'readyok') { this._ready(); }
    else if (line.startsWith('bestmove')) {
      const r = this.resolver; this.resolver = null;
      if (r) r(line.split(' ')[1]);
    } else if (this.onDepth && line.startsWith('info depth')) {
      this.onDepth(+line.split(' ')[2]);
    }
  }
  // Renvoie le meilleur coup au format UCI ("e2e4", "e7e8q").
  search(uciMoves, elo, time) {
    const run = async () => {
      await this.ready;
      this.post('setoption name UCI_LimitStrength value ' + (elo ? 'true' : 'false'));
      if (elo) this.post('setoption name UCI_Elo value ' + elo);
      this.post('position startpos' + (uciMoves.length ? ' moves ' + uciMoves.join(' ') : ''));
      return new Promise((res) => { this.resolver = res; this.post('go movetime ' + Math.round(time)); });
    };
    const p = this.chain.then(run);
    this.chain = p.catch(() => {});
    return p;
  }
  stop() { if (this.w && this.resolver) this.post('stop'); }
  newGame() { this.chain = this.chain.then(() => this.ready).then(() => this.post('ucinewgame')).catch(() => {}); }
}

const engine = new Engine();
engine.ready.catch(() => toast('Impossible de charger le moteur Stockfish. Ouvrez le jeu via un serveur web (http://).', 8000));

// ---------------------------------------------------------------- sons

let actx = null;
function sound(kind) {
  if (!soundOn) return;
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === 'suspended') actx.resume();
    const t = actx.currentTime;
    const knock = (at, freq, vol, dur) => {
      const len = Math.floor(actx.sampleRate * dur);
      const buf = actx.createBuffer(1, len, actx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
      const src = actx.createBufferSource(); src.buffer = buf;
      const f = actx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = 1.2;
      const g = actx.createGain(); g.gain.value = vol;
      src.connect(f).connect(g).connect(actx.destination); src.start(t + at);
    };
    const tone = (at, freq, vol, dur) => {
      const o = actx.createOscillator(); o.type = 'sine'; o.frequency.value = freq;
      const g = actx.createGain();
      g.gain.setValueAtTime(vol, t + at); g.gain.exponentialRampToValueAtTime(0.001, t + at + dur);
      o.connect(g).connect(actx.destination); o.start(t + at); o.stop(t + at + dur);
    };
    if (kind === 'move') knock(0, 900, 0.9, 0.07);
    else if (kind === 'capture') { knock(0, 1500, 1.0, 0.05); knock(0.045, 600, 1.0, 0.09); }
    else if (kind === 'check') { knock(0, 900, 0.9, 0.07); tone(0.03, 880, 0.12, 0.18); }
    else if (kind === 'end') { tone(0, 523, 0.15, 0.35); tone(0.16, 659, 0.15, 0.35); tone(0.32, 784, 0.15, 0.6); }
  } catch { /* audio indisponible */ }
}

// ---------------------------------------------------------------- état

const board = $('board'), squaresEl = $('squares'), piecesEl = $('pieces');
const G = {
  chess: new Chess(), moves: [], fens: [], view: 0, orient: 'w', human: 'w',
  mode: 'bot', bot: BOTS[6], over: null, searchId: 0, thinking: false, depth: 0,
  hint: null, sel: null, targets: [], promoPending: null, autoFlip: false,
  clock: { on: false, w: 0, b: 0, inc: 0, running: false, last: 0 },
};
let pieceEls = {};
let drag = null;

const other = (c) => (c === 'w' ? 'b' : 'w');
const atLatest = () => G.view === G.fens.length - 1;
const uciMoves = () => G.moves.map((m) => m.from + m.to + (m.promotion || ''));
function canMove() {
  if (G.over || !atLatest() || G.promoPending) return false;
  return G.mode === 'friend' || G.chess.turn() === G.human;
}

function newGame() {
  G.searchId++;
  engine.stop();
  engine.newGame();
  G.chess = new Chess();
  G.moves = []; G.fens = [G.chess.fen()]; G.view = 0;
  G.mode = cfg.mode; G.bot = BOTS[cfg.bot]; G.autoFlip = cfg.autoFlip;
  G.human = cfg.mode === 'friend' ? 'w' : cfg.color === 'r' ? (Math.random() < 0.5 ? 'w' : 'b') : cfg.color;
  G.orient = G.human;
  G.over = null; G.thinking = false; G.hint = null; G.sel = null; G.targets = []; G.promoPending = null;
  const tc = TCS[cfg.tc].tc;
  G.clock = tc
    ? { on: true, w: tc[0] * 60000, b: tc[0] * 60000, inc: tc[1] * 1000, running: false, last: 0 }
    : { on: false, w: 0, b: 0, inc: 0, running: false, last: 0 };
  $('endCard').hidden = true; $('promo').hidden = true;
  buildSquares();
  render();
  maybeBot();
}

// ---------------------------------------------------------------- rendu

function xy(sq) {
  const f = sq.charCodeAt(0) - 97, r = +sq[1] - 1;
  return G.orient === 'w' ? [f, 7 - r] : [7 - f, r];
}
function sqAt(clientX, clientY) {
  const b = board.getBoundingClientRect();
  const x = Math.floor(((clientX - b.left) / b.width) * 8), y = Math.floor(((clientY - b.top) / b.height) * 8);
  if (x < 0 || x > 7 || y < 0 || y > 7) return null;
  const f = G.orient === 'w' ? x : 7 - x, r = G.orient === 'w' ? 7 - y : y;
  return 'abcdefgh'[f] + (r + 1);
}

function buildSquares() {
  squaresEl.innerHTML = '';
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
    const f = G.orient === 'w' ? x : 7 - x, r = G.orient === 'w' ? 7 - y : y;
    const d = document.createElement('div');
    d.className = 'sq ' + ((f + r) % 2 ? 'l' : 'd');
    d.dataset.sq = 'abcdefgh'[f] + (r + 1);
    if (y === 7) d.innerHTML += `<span class="cf">${'abcdefgh'[f]}</span>`;
    if (x === 0) d.innerHTML += `<span class="cr">${r + 1}</span>`;
    squaresEl.appendChild(d);
  }
}
const sqEl = (sq) => squaresEl.querySelector(`[data-sq="${sq}"]`);

function render(anim) {
  const view = atLatest() ? G.chess : new Chess(G.fens[G.view]);
  renderPieces(view, anim);
  renderMarks(view);
  renderPlayers(view);
  renderMoves();
  renderStatus();
  const busy = G.thinking;
  $('btnUndo').disabled = !!G.over || G.moves.length === 0 || (G.mode === 'bot' && !G.moves.some((m) => m.color === G.human));
  $('btnHint').disabled = !canMove() || busy || engine.failed;
  $('btnResign').disabled = !!G.over || G.moves.length === 0;
  $('btnPgn').disabled = G.moves.length === 0;
  $('navFirst').disabled = $('navPrev').disabled = G.view === 0;
  $('navNext').disabled = $('navLast').disabled = atLatest();
  $('btnSound').textContent = soundOn ? '🔊 Son' : '🔇 Muet';
  board.classList.toggle('can', canMove());
}

function renderPieces(view, anim) {
  piecesEl.innerHTML = '';
  pieceEls = {};
  for (const row of view.board()) for (const p of row) {
    if (!p) continue;
    const [x, y] = xy(p.square);
    const el = document.createElement('div');
    el.className = 'piece';
    el.style.left = x * 12.5 + '%'; el.style.top = y * 12.5 + '%';
    el.style.backgroundImage = `url(pieces/${p.color}${p.type}.svg)`;
    piecesEl.appendChild(el);
    pieceEls[p.square] = el;
  }
  if (anim) {
    slide(anim.from, anim.to);
    if (anim.flags.includes('k') || anim.flags.includes('q')) {
      const rank = anim.to[1], k = anim.flags.includes('k');
      slide((k ? 'h' : 'a') + rank, (k ? 'f' : 'd') + rank);
    }
  }
}
function slide(from, to) {
  const el = pieceEls[to];
  if (!el || !el.animate) return;
  const [fx, fy] = xy(from), [tx, ty] = xy(to);
  el.style.zIndex = 5;
  el.animate([{ transform: `translate(${(fx - tx) * 100}%, ${(fy - ty) * 100}%)` }, { transform: 'none' }],
    { duration: 170, easing: 'cubic-bezier(.2,.7,.3,1)' });
}

function renderMarks(view) {
  for (const d of squaresEl.children) d.classList.remove('last', 'sel', 'tgt', 'cap', 'chk', 'hint', 'own', 'over');
  const last = G.moves[G.view - 1];
  if (last) { sqEl(last.from).classList.add('last'); sqEl(last.to).classList.add('last'); }
  if (view.isCheck()) {
    for (const row of view.board()) for (const p of row) {
      if (p && p.type === 'k' && p.color === view.turn()) sqEl(p.square).classList.add('chk');
    }
  }
  if (!atLatest()) return;
  if (G.hint) { sqEl(G.hint.from).classList.add('hint'); sqEl(G.hint.to).classList.add('hint'); }
  if (canMove()) {
    for (const row of view.board()) for (const p of row) if (p && p.color === view.turn()) sqEl(p.square).classList.add('own');
  }
  if (G.sel) {
    sqEl(G.sel).classList.add('sel');
    for (const m of G.targets) {
      const e = sqEl(m.to); e.classList.add('tgt');
      if (m.captured) e.classList.add('cap');
    }
  }
}

const VAL = { p: 1, n: 3, b: 3, r: 5, q: 9 };
const START = { p: 8, n: 2, b: 2, r: 2, q: 1 };
function material(view) {
  const cnt = { w: { p: 0, n: 0, b: 0, r: 0, q: 0 }, b: { p: 0, n: 0, b: 0, r: 0, q: 0 } };
  let score = 0;
  for (const row of view.board()) for (const p of row) {
    if (!p || p.type === 'k') continue;
    cnt[p.color][p.type]++;
    score += (p.color === 'w' ? 1 : -1) * VAL[p.type];
  }
  return { cnt, score };
}
function fmtClock(ms) {
  ms = Math.max(0, ms);
  const s = Math.floor(ms / 1000), m = Math.floor(s / 60);
  if (ms < 10000) return `0:0${s}.${Math.floor((ms % 1000) / 100)}`;
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}
function playerInfo(color) {
  if (G.mode === 'friend') return { name: color === 'w' ? 'Blancs' : 'Noirs', sub: '', e: color === 'w' ? '♔' : '♚' };
  if (color === G.human) return { name: 'Vous', sub: color === 'w' ? 'Blancs' : 'Noirs', e: '🙂' };
  return { name: G.bot.name, sub: G.bot.label, e: G.bot.e };
}
function renderPlayers(view) {
  const { cnt, score } = material(view);
  const fill = (el, color) => {
    const info = playerInfo(color), opp = other(color);
    let caps = '';
    for (const t of ['q', 'r', 'b', 'n', 'p']) {
      const n = Math.max(0, START[t] - cnt[opp][t]);
      if (n) caps += `<i style="background-image:url(pieces/${opp}${t}.svg)"></i>`.repeat(n) + '<i class="gap"></i>';
    }
    const adv = color === 'w' ? score : -score;
    const turn = !G.over && G.chess.turn() === color;
    el.className = 'player' + (turn ? ' turn' : '');
    el.innerHTML = `<div class="avatar">${info.e}</div>
      <div class="pinfo"><div class="pname">${info.name}${info.sub ? `<small>${info.sub}</small>` : ''}</div>
      <div class="captured">${caps}${adv > 0 ? `<b>+${adv}</b>` : ''}</div></div>
      ${G.clock.on ? `<div class="clock" data-c="${color}"></div>` : ''}`;
  };
  fill($('playerBottom'), G.orient);
  fill($('playerTop'), other(G.orient));
  paintClocks();
}
function paintClocks() {
  if (!G.clock.on) return;
  for (const el of document.querySelectorAll('.clock')) {
    const c = el.dataset.c;
    el.textContent = fmtClock(G.clock[c]);
    el.classList.toggle('on', !G.over && G.chess.turn() === c);
    el.classList.toggle('low', G.clock[c] < 20000);
  }
}

const FR = { N: 'C', B: 'F', R: 'T', Q: 'D', K: 'R' };
const sanFr = (san) => san.replace(/[NBRQK]/g, (c) => FR[c]);
function renderMoves() {
  const el = $('moves');
  if (!G.moves.length) { el.innerHTML = '<div class="empty">La partie commence. Aux Blancs de jouer.</div>'; return; }
  let h = '';
  G.moves.forEach((m, i) => {
    if (i % 2 === 0) h += `<div class="n">${i / 2 + 1}.</div>`;
    h += `<div class="m${G.view === i + 1 ? ' cur' : ''}" data-i="${i + 1}">${sanFr(m.san)}</div>`;
  });
  el.innerHTML = h;
  const cur = el.querySelector('.cur');
  if (cur) cur.scrollIntoView({ block: 'nearest' });
}

function renderStatus() {
  let s;
  if (G.over) s = `${G.over.title} — ${G.over.reason}`;
  else if (!atLatest()) s = `Relecture : coup ${G.view} / ${G.moves.length}`;
  else if (G.thinking) s = `${G.bot.name} réfléchit…` + (G.depth > 1 ? ` (profondeur ${G.depth})` : '');
  else {
    s = 'Trait aux ' + (G.chess.turn() === 'w' ? 'Blancs' : 'Noirs');
    if (G.chess.isCheck()) s += ' — Échec !';
  }
  $('status').textContent = s;
}

// ---------------------------------------------------------------- coups

function play(m, animate = true) {
  tickClock();
  if (G.over) return false;
  let mv;
  try { mv = G.chess.move(m); } catch { return false; }
  if (G.clock.on) {
    if (G.clock.running) G.clock[mv.color] += G.clock.inc;
    G.clock.running = true; G.clock.last = performance.now();
  }
  G.moves.push(mv); G.fens.push(G.chess.fen()); G.view = G.fens.length - 1;
  G.sel = null; G.targets = []; G.hint = null;
  if (G.mode === 'friend' && G.autoFlip && !G.chess.isGameOver()) {
    G.orient = G.chess.turn(); buildSquares(); animate = false;
  }
  checkEnd();
  sound(G.over ? 'end' : G.chess.isCheck() ? 'check' : mv.captured ? 'capture' : 'move');
  render(animate ? mv : null);
  maybeBot();
  return true;
}

function checkEnd() {
  const c = G.chess;
  if (c.isCheckmate()) finish(other(c.turn()), 'par échec et mat');
  else if (c.isStalemate()) finish(null, 'pat');
  else if (c.isInsufficientMaterial()) finish(null, 'matériel insuffisant');
  else if (c.isThreefoldRepetition()) finish(null, 'triple répétition');
  else if (c.isDraw()) finish(null, 'règle des 50 coups');
}

function finish(winner, reason) {
  G.searchId++; engine.stop();
  G.thinking = false; G.clock.running = false;
  let title;
  if (!winner) title = 'Partie nulle';
  else if (G.mode === 'bot') title = winner === G.human ? 'Victoire ! 🎉' : 'Défaite';
  else title = winner === 'w' ? 'Les Blancs gagnent' : 'Les Noirs gagnent';
  G.over = { winner, title, reason, result: !winner ? '1/2-1/2' : winner === 'w' ? '1-0' : '0-1' };
  $('endTitle').textContent = title; $('endReason').textContent = reason;
  $('endCard').hidden = false;
}

async function maybeBot() {
  if (G.mode !== 'bot' || G.over || G.chess.turn() === G.human) return;
  const id = ++G.searchId, t0 = performance.now();
  G.thinking = true; G.depth = 0;
  renderStatus();
  let time = G.bot.time;
  if (G.clock.on) time = Math.min(time, Math.max(120, G.clock[G.chess.turn()] / 30 + G.clock.inc * 0.6));
  let best;
  try { best = await engine.search(uciMoves(), G.bot.elo, time); } catch { G.thinking = false; render(); return; }
  if (id !== G.searchId) return;
  const wait = 450 - (performance.now() - t0);
  if (wait > 0 && !G.clock.on) await new Promise((r) => setTimeout(r, wait));
  if (id !== G.searchId) return;
  G.thinking = false;
  if (!best || best === '(none)') { render(); return; }
  const wasViewing = !atLatest(), v = G.view;
  play({ from: best.slice(0, 2), to: best.slice(2, 4), promotion: best[4] });
  if (wasViewing) { G.view = v; render(); }
}
engine.onDepth = (d) => { if (G.thinking && d !== G.depth) { G.depth = d; renderStatus(); } };

function undo() {
  if (G.over || !G.moves.length) return;
  G.searchId++; engine.stop(); G.thinking = false;
  const pop = () => { G.chess.undo(); G.moves.pop(); G.fens.pop(); };
  pop();
  if (G.mode === 'bot') while (G.moves.length && G.chess.turn() !== G.human) pop();
  G.view = G.fens.length - 1; G.sel = null; G.targets = []; G.hint = null;
  if (G.clock.on) { G.clock.last = performance.now(); if (!G.moves.length) G.clock.running = false; }
  if (G.mode === 'friend' && G.autoFlip) { G.orient = G.chess.turn(); buildSquares(); }
  render();
  maybeBot();
}

async function hint() {
  if (!canMove() || G.thinking) return;
  const id = G.searchId, ply = G.moves.length;
  $('btnHint').disabled = true; $('btnHint').textContent = '💡 …';
  let best;
  try { best = await engine.search(uciMoves(), null, 700); } catch { best = null; }
  $('btnHint').textContent = '💡 Indice';
  if (best && best !== '(none)' && id === G.searchId && ply === G.moves.length && !G.over) {
    G.hint = { from: best.slice(0, 2), to: best.slice(2, 4) };
  }
  render();
}

function resign() {
  if (G.over || !G.moves.length) return;
  const loser = G.mode === 'bot' ? G.human : G.chess.turn();
  if (!confirm(G.mode === 'bot' ? 'Abandonner la partie ?' : `Les ${loser === 'w' ? 'Blancs' : 'Noirs'} abandonnent ?`)) return;
  finish(other(loser), 'par abandon');
  sound('end'); render();
}

// ---------------------------------------------------------------- pendule

function tickClock() {
  const c = G.clock;
  if (!c.on || !c.running || G.over) return;
  const now = performance.now(), side = G.chess.turn();
  c[side] -= now - c.last; c.last = now;
  if (c[side] <= 0) {
    c[side] = 0;
    finish(other(side), 'au temps');
    sound('end'); render();
  }
}
setInterval(() => { tickClock(); paintClocks(); }, 100);

// ---------------------------------------------------------------- interaction

function select(sq) {
  G.sel = sq;
  G.targets = sq ? G.chess.moves({ square: sq, verbose: true }) : [];
  renderMarks(G.chess);
}

function tryMove(from, to, animate) {
  const cands = G.targets.filter((m) => m.from === from && m.to === to);
  if (!cands.length) return false;
  if (cands.some((m) => m.promotion)) { askPromotion(from, to, animate); return true; }
  return play({ from, to }, animate);
}

function askPromotion(from, to, animate) {
  const color = G.chess.turn(), el = $('promo');
  G.promoPending = { from, to };
  el.innerHTML = '';
  for (const t of ['q', 'r', 'b', 'n']) {
    const b = document.createElement('button');
    b.style.backgroundImage = `url(pieces/${color}${t}.svg)`;
    b.title = { q: 'Dame', r: 'Tour', b: 'Fou', n: 'Cavalier' }[t];
    b.onclick = (ev) => { ev.stopPropagation(); el.hidden = true; G.promoPending = null; play({ from, to, promotion: t }, animate); };
    el.appendChild(b);
  }
  el.hidden = false;
  render();
}
$('promo').addEventListener('pointerdown', (ev) => {
  ev.stopPropagation();
  if (ev.target === $('promo')) { $('promo').hidden = true; G.promoPending = null; select(null); render(); }
});

board.addEventListener('pointerdown', (ev) => {
  if (ev.button > 0 || !canMove()) return;
  const sq = sqAt(ev.clientX, ev.clientY);
  if (!sq) return;
  ev.preventDefault();
  const p = G.chess.get(sq);
  const own = p && p.color === G.chess.turn();
  if (G.sel && !own) {
    if (!tryMove(G.sel, sq, true)) select(null);
    return;
  }
  if (!own) return;
  const wasSel = G.sel === sq;
  select(sq);
  const el = pieceEls[sq];
  drag = { from: sq, el, x0: ev.clientX, y0: ev.clientY, moved: false, wasSel, overSq: null };
  try { board.setPointerCapture(ev.pointerId); } catch { /* pointeur non capturable */ }
});

board.addEventListener('pointermove', (ev) => {
  if (!drag) return;
  const dx = ev.clientX - drag.x0, dy = ev.clientY - drag.y0;
  if (!drag.moved && Math.hypot(dx, dy) < 5) return;
  drag.moved = true;
  drag.el.classList.add('drag');
  // centre la pièce sous le pointeur
  const b = board.getBoundingClientRect(), s = b.width / 8;
  const [x, y] = xy(drag.from);
  const tx = ev.clientX - b.left - (x + 0.5) * s, ty = ev.clientY - b.top - (y + 0.5) * s;
  drag.el.style.transform = `translate(${tx}px, ${ty}px) scale(1.12)`;
  const over = sqAt(ev.clientX, ev.clientY);
  if (over !== drag.overSq) {
    if (drag.overSq) sqEl(drag.overSq).classList.remove('over');
    if (over) sqEl(over).classList.add('over');
    drag.overSq = over;
  }
});

function endDrag(ev, cancelled) {
  if (!drag) return;
  const d = drag; drag = null;
  if (d.overSq) sqEl(d.overSq).classList.remove('over');
  d.el.classList.remove('drag'); d.el.style.transform = '';
  if (cancelled) return;
  const sq = sqAt(ev.clientX, ev.clientY);
  if (d.moved && sq && sq !== d.from) {
    if (!tryMove(d.from, sq, false)) renderMarks(G.chess);
  } else if (!d.moved && d.wasSel) {
    select(null);
  }
}
board.addEventListener('pointerup', (ev) => endDrag(ev, false));
board.addEventListener('pointercancel', (ev) => endDrag(ev, true));
board.addEventListener('contextmenu', (ev) => ev.preventDefault());

function goto(i) {
  i = Math.max(0, Math.min(G.fens.length - 1, i));
  if (i === G.view) return;
  const fwd = i === G.view + 1;
  G.view = i; G.sel = null; G.targets = [];
  render(fwd ? G.moves[i - 1] : null);
  if (fwd) sound(G.moves[i - 1].captured ? 'capture' : 'move');
}

$('moves').addEventListener('click', (ev) => { const m = ev.target.closest('.m'); if (m) goto(+m.dataset.i); });
$('navFirst').onclick = () => goto(0);
$('navPrev').onclick = () => goto(G.view - 1);
$('navNext').onclick = () => goto(G.view + 1);
$('navLast').onclick = () => goto(G.fens.length - 1);
$('btnUndo').onclick = undo;
$('btnHint').onclick = hint;
$('btnResign').onclick = resign;
$('btnFlip').onclick = () => { G.orient = other(G.orient); buildSquares(); render(); };
$('btnSound').onclick = () => { soundOn = !soundOn; store.set('sound', soundOn); render(); sound('move'); };
$('btnPgn').onclick = async () => {
  const tags = {
    Event: 'Partie amicale', Date: new Date().toISOString().slice(0, 10).replace(/-/g, '.'),
    White: playerInfo('w').name, Black: playerInfo('b').name, Result: G.over ? G.over.result : '*',
  };
  const head = Object.entries(tags).map(([k, v]) => `[${k} "${v}"]`).join('\n');
  let body = '';
  G.moves.forEach((m, i) => { body += (i % 2 === 0 ? `${i / 2 + 1}. ` : '') + m.san + ' '; });
  const pgn = `${head}\n\n${body}${tags.Result}\n`;
  try { await navigator.clipboard.writeText(pgn); toast('PGN copié dans le presse-papiers'); }
  catch { prompt('Copiez le PGN :', pgn); }
};
document.addEventListener('keydown', (ev) => {
  if (!$('setup').hidden || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (ev.key === 'ArrowLeft') goto(G.view - 1);
  else if (ev.key === 'ArrowRight') goto(G.view + 1);
  else if (ev.key === 'ArrowUp') goto(0);
  else if (ev.key === 'ArrowDown') goto(G.fens.length - 1);
  else if (ev.key === 'f') $('btnFlip').click();
  else return;
  ev.preventDefault();
});

let toastTimer;
function toast(msg, ms = 2500) {
  const t = $('toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

// ---------------------------------------------------------------- dialogue de configuration

function seg(el, get, set) {
  const paint = () => { for (const b of el.children) b.classList.toggle('on', b.dataset.v === String(get())); };
  el.addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) { set(b.dataset.v); paint(); paintSetup(); } });
  paint();
}
function paintSetup() {
  $('botSection').hidden = cfg.mode !== 'bot';
  $('friendSection').hidden = cfg.mode !== 'friend';
  for (const b of $('bots').children) b.classList.toggle('on', +b.dataset.i === cfg.bot);
  $('botDesc').textContent = BOTS[cfg.bot].desc;
}
$('bots').innerHTML = BOTS.map((b, i) =>
  `<button class="bot${b.top ? ' top' : ''}" data-i="${i}"><span class="e">${b.e}</span><span class="nm">${b.name}</span><span class="el">Elo ${b.label}</span></button>`).join('');
$('bots').insertAdjacentHTML('afterend', '<p class="bot-desc" id="botDesc"></p>');
$('bots').addEventListener('click', (ev) => { const b = ev.target.closest('.bot'); if (b) { cfg.bot = +b.dataset.i; paintSetup(); } });
$('segTc').innerHTML = TCS.map((t, i) => `<button data-v="${i}">${t.label}</button>`).join('');
seg($('segMode'), () => cfg.mode, (v) => { cfg.mode = v; });
seg($('segColor'), () => cfg.color, (v) => { cfg.color = v; });
seg($('segTc'), () => cfg.tc, (v) => { cfg.tc = +v; });
$('autoFlip').checked = cfg.autoFlip;
$('autoFlip').onchange = () => { cfg.autoFlip = $('autoFlip').checked; };
paintSetup();

let started = false;
function openSetup() { $('btnCancel').hidden = !started; $('setup').hidden = false; }
$('btnNew').onclick = openSetup;
$('btnEndNew').onclick = openSetup;
$('btnCancel').onclick = () => { $('setup').hidden = true; };
$('btnStart').onclick = () => { store.set('cfg', cfg); started = true; $('setup').hidden = true; newGame(); };
$('btnRematch').onclick = () => {
  if (G.mode === 'bot' && cfg.color !== 'r') cfg.color = other(G.human); // on échange les couleurs
  newGame();
};
$('btnEndClose').onclick = () => { $('endCard').hidden = true; };

// échiquier d'attente derrière le dialogue
G.fens = [G.chess.fen()];
buildSquares();
render();
openSetup();
