<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<title>教学动画骨架</title>
<script src="assets/vendor/gsap.min.js"></script>
<style>
/* ── 字体：必须自带 woff2，系统字体名会被 lint 拒绝 ───────────────── */
@font-face{font-family:"Song";src:url("assets/fonts/SongtiSC-Regular.woff2") format("woff2");font-weight:400;font-display:block}
@font-face{font-family:"Song";src:url("assets/fonts/SongtiSC-Bold.woff2") format("woff2");font-weight:700;font-display:block}
@font-face{font-family:"Hei";src:url("assets/fonts/HiraginoSansGB-W3.woff2") format("woff2");font-weight:400;font-display:block}
@font-face{font-family:"Hei";src:url("assets/fonts/HiraginoSansGB-W6.woff2") format("woff2");font-weight:700;font-display:block}

/* ── 色板：六个颜色各有职责，不要临时加 ───────────────────────────── */
:root{
  --paper:#F4EFE4;   /* 纸面 */
  --ink:#16202A;     /* 墨色：主线条与文字 */
  --green:#0E6B5E;   /* 可达 / 增益 */
  --red:#A8341A;     /* 代价 / 损失 */
  --grey:#485866;    /* 辅助与注释 */
  --gold:#C8901E;    /* 高亮 */
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);font-family:"Song",serif;color:var(--ink)}
#root{position:relative;width:1920px;height:1080px;overflow:hidden}
.clip{position:absolute}

/* ── 纸面层 ──────────────────────────────────────────────────────── */
#paper{inset:0;width:1920px;height:1080px}

/* ── 图形层 ──────────────────────────────────────────────────────── */
#stage{inset:0}
svg#art{position:absolute;left:0;top:0;width:1920px;height:1080px}
.grid{stroke:var(--ink);stroke-width:1;opacity:.11}
.axis{stroke:var(--ink);stroke-width:3;stroke-linecap:square;fill:none}
.tick{font-family:"Hei",sans-serif;font-size:19px;fill:var(--grey);text-anchor:middle}
.tick.end{text-anchor:end}
.axis-title{font-family:"Hei",sans-serif;font-size:26px;fill:var(--ink);font-weight:700;letter-spacing:.04em}
#curve{fill:none;stroke:var(--ink);stroke-width:8;stroke-linecap:round}
#curve-halo{fill:none;stroke:var(--gold);stroke-width:2;opacity:0}
#tan{stroke:var(--red);stroke-width:4;stroke-linecap:round;opacity:0}
#cursor-halo{fill:var(--green);opacity:.16}
#cursor{fill:var(--green);stroke:var(--paper);stroke-width:3}
.pt{opacity:0}
.pt circle{stroke:var(--paper);stroke-width:3}
.pt text{font-family:"Hei",sans-serif;font-size:34px;font-weight:700}

/* ── 左栏信息区（不对称版面：不要把内容居中摆） ───────────────────── */
#left{left:96px;top:0;width:464px;height:1080px}
#kicker{position:absolute;top:148px;font-family:"Hei",sans-serif;font-size:22px;
        letter-spacing:.22em;color:var(--grey)}
.hl{position:absolute;top:190px;width:464px;font-size:52px;line-height:1.34;font-weight:700;opacity:0}
.bd{position:absolute;top:436px;width:440px;font-size:26px;line-height:1.78;color:#2C3A45;opacity:0}
.bd b{color:var(--green);font-weight:700}
.dl{position:absolute;top:600px;width:464px;font-family:"Hei",sans-serif;font-size:26px;opacity:0}
.dl .up{color:var(--green)} .dl .down{color:var(--red)}

/* ── 读数：纵向数字带，靠 transform 跳档 ─────────────────────────── */
#readout{position:absolute;top:700px;width:464px;opacity:0}
.ro-row{display:flex;align-items:baseline;justify-content:space-between;padding:12px 0;
        border-top:1px solid rgba(22,32,42,.16)}
.ro-row:last-child{border-bottom:1px solid rgba(22,32,42,.16)}
.ro-label{font-family:"Hei",sans-serif;font-size:22px;color:var(--grey);letter-spacing:.08em}
.ro-wrap{display:flex;align-items:baseline}
.odo{display:inline-block;height:64px;overflow:hidden}
.strip{display:block}
.strip span{display:block;height:64px;font-family:"Hei",sans-serif;font-size:64px;font-weight:700;
            line-height:64px;text-align:right;font-variant-numeric:tabular-nums}
.ro-unit{font-size:20px;color:var(--grey);margin-left:8px}

#badge{position:absolute;left:96px;bottom:64px;font-family:"Hei",sans-serif;font-size:19px;
       color:var(--grey);letter-spacing:.14em}

/* ── 图上说明卡与收口页 ──────────────────────────────────────────── */
.card{position:absolute;padding:20px 26px;font-family:"Hei",sans-serif;font-size:24px;line-height:1.62}
#cardA{left:1504px;top:150px;width:340px;opacity:0}
#words{position:absolute;left:96px;top:322px;width:1728px;display:flex;gap:84px;
       justify-content:center;font-size:76px;font-weight:700;opacity:0}
#words span{opacity:0}
#endTitle{position:absolute;left:96px;top:478px;width:1400px;font-size:64px;font-weight:700;
          line-height:1.5;opacity:0}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-duration="__TOTAL__" data-fps="30">

  <div id="paper" class="clip" data-start="0" data-duration="__TOTAL__" data-track-index="0">
    <svg width="1920" height="1080" viewBox="0 0 1920 1080" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="grainF" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="5" result="n"/>
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0.09  0 0 0 0 0.13  0 0 0 0 0.16  0 0 0 0.05 0"/>
        </filter>
        <radialGradient id="vig" cx="46%" cy="42%" r="78%">
          <stop offset="55%" stop-color="#000" stop-opacity="0"/>
          <stop offset="100%" stop-color="#4a3b26" stop-opacity="0.16"/>
        </radialGradient>
      </defs>
      <rect width="1920" height="1080" fill="#F4EFE4"/>
      <rect width="1920" height="1080" fill="#F4EFE4" filter="url(#grainF)" opacity=".55"/>
      <rect id="vigRect" width="1920" height="1080" fill="url(#vig)"/>
    </svg>
  </div>

  <div id="stage" class="clip" data-start="0" data-duration="__TOTAL__" data-track-index="1">
    <svg id="art" viewBox="0 0 1920 1080" xmlns="http://www.w3.org/2000/svg">
      <g id="grid" opacity="0">__GRID__</g>
      <g id="axes" opacity="0">
        <path class="axis" d="M 700 980 L 700 190"/>
        <path class="axis" d="M 680 960 L 1834 960"/>
        <polygon points="700,176 689,204 711,204" fill="#16202A"/>
        <polygon points="1848,960 1820,949 1820,971" fill="#16202A"/>
        <text x="700" y="150" class="axis-title">__AXIS_Y__</text>
        <text x="1824" y="1046" class="axis-title" text-anchor="end">__AXIS_X__</text>
      </g>
      <g id="ticks" opacity="0">__TICKS__</g>

      <path id="curve-halo" d="__CURVE__" stroke-dasharray="__LEN__" stroke-dashoffset="__LEN__"/>
      <path id="curve" d="__CURVE__" stroke-dasharray="__LEN__" stroke-dashoffset="__LEN__"/>
      <line id="tan" x1="0" y1="0" x2="0" y2="0"/>

      <g id="cursorG" opacity="0">
        <circle id="cursor-halo" r="26" cx="0" cy="0"/>
        <circle id="cursor" r="11" cx="0" cy="0"/>
      </g>

      <g class="pt" data-name="A"><circle cx="__AX__" cy="__AY__" r="12" fill="#0E6B5E"/><text x="__AX__" y="__AY__" dx="-52" dy="-28">A</text></g>
      <g class="pt" data-name="B"><circle cx="__BX__" cy="__BY__" r="12" fill="#0E6B5E"/><text x="__BX__" y="__BY__" dx="18" dy="52">B</text></g>
    </svg>
  </div>

  <div id="left" class="clip" data-start="0" data-duration="__TOTAL__" data-track-index="2">
    <div id="kicker">__KICKER__</div>

    <!-- 每段一个标题，预置好，用 opacity 切换；不要用 tl.call 改 innerHTML -->
    <div class="hl" id="hl1">__HL1__</div>
    <div class="hl" id="hl2">__HL2__</div>
    <div class="hl" id="hl3">__HL3__</div>
    <div class="hl" id="hl4">__HL3__</div>

    <div class="bd" id="bd2">__BD2__</div>

    <div class="dl" id="dl3"><span class="up">__DL3__</span></div>

    <div id="readout">
      <div class="ro-row"><span class="ro-label">__R1__</span><span class="ro-wrap"><span class="odo"><span class="strip" id="odoA">__ROWS_A__</span></span><span class="ro-unit">__U1__</span></span></div>
      <div class="ro-row"><span class="ro-label">__R2__</span><span class="ro-wrap"><span class="odo"><span class="strip" id="odoB">__ROWS_B__</span></span><span class="ro-unit">__U2__</span></span></div>
    </div>
    <div id="badge">__BADGE__</div>
  </div>

  <div id="cardA" class="card clip" data-start="__CARD_T__" data-duration="__CARD_D__" data-track-index="3">
    __CARD_BODY__
  </div>

  <div id="words" class="clip" data-start="__W_T__" data-duration="__W_D__" data-track-index="3">
    <span>__W1__</span><span>__W2__</span><span>__W3__</span><span>__W4__</span><span>__W5__</span>
  </div>
  <div id="endTitle" class="clip" data-start="__W_T__" data-duration="__W_D__" data-track-index="3">__END_TITLE__</div>

  <!-- 旁白：必须直接挂在 composition root 下，不能塞进任何 wrapper -->
__AUDIO__
</div>

<script>
const TL = __TLJSON__;
const S = TL.seg;
const tl = gsap.timeline({paused:true});

/* ══ 初始状态兜底 ═══════════════════════════════════════════════════
   GSAP 的 fromTo 默认 immediateRender:true，多个 tween 碰同一属性时，
   最后构建的那个会立即应用它的 from 值，覆盖 CSS 初始态。
   所以：所有 fromTo 加 immediateRender:false，并在 t=0 用 set 锁死。 */
tl.set(["#tan","#curve-halo","#cursorG","#cardA","#words"], {opacity:0}, 0);
tl.set(["#axes","#ticks","#grid","#readout"], {opacity:0}, 0);
tl.set(".pt", {opacity:0}, 0);
tl.set("#words span", {opacity:0}, 0);
tl.set("#endTitle", {opacity:0}, 0);

/* ══ 文本层切换 ═════════════════════════════════════════════════════
   构建时同步生成 tween，不依赖回调，逐帧 seek 也稳定。 */
let curHL = null, curBD = null, curDL = null;
function hl(id, at){
  if (curHL) tl.to(curHL, {opacity:0, duration:0.3}, Math.max(0, at-0.3));
  tl.fromTo(id, {opacity:0, y:18}, {opacity:1, y:0, duration:0.75, ease:"power3.out", immediateRender:false}, at);
  curHL = id;
}
function bd(id, at){
  if (curBD) tl.to(curBD, {opacity:0, duration:0.3}, Math.max(0, at-0.3));
  tl.fromTo(id, {opacity:0, y:12}, {opacity:1, y:0, duration:0.8, immediateRender:false}, at);
  curBD = id;
}
function dl(id, at){
  if (curDL) tl.to(curDL, {opacity:0, duration:0.3}, Math.max(0, at-0.3));
  tl.fromTo(id, {opacity:0, y:10}, {opacity:1, y:0, duration:0.6, immediateRender:false}, at);
  curDL = id;
}

/* 读数：逐档瞬时跳。长链条微 tween 在逐帧 seek 下会丢帧，别用它做滚动。 */
const ROW = 64;
function odo(sel, fromIdx, toIdx, at, dur){
  const n = Math.abs(toIdx - fromIdx);
  if (n === 0) { tl.set(sel, {y: -toIdx*ROW}, at); return; }
  for (let i = 0; i <= n; i++) {
    const idx = fromIdx + (toIdx - fromIdx) * i / n;
    tl.set(sel, {y: -Math.round(idx)*ROW}, at + dur * i / n);
  }
}

/* 游标：预计算坐标后 set，不要用 MotionPathPlugin */
function cursorTo(x, y, at){
  tl.set("#cursor", {attr:{cx:x, cy:y}}, at);
  tl.set("#cursor-halo", {attr:{cx:x, cy:y}}, at);
}

/* ══ 背景呼吸：全程极慢，提供底噪般的生命感 ═══════════════════════ */
tl.to("#vigRect", {opacity:.75, duration:TL.total/2, yoyo:true, repeat:1, ease:"sine.inOut"}, 0);

/* ══ 逐段动画 ═══════════════════════════════════════════════════════
   三层节奏：主运动一次一个，次要跟旁白，背景不停。 */

/* s1 钩子：前五秒必须给出全片最强的信息密度 */
const s1 = S.s1[0];
tl.fromTo("#kicker", {opacity:0}, {opacity:1, duration:0.6, immediateRender:false}, s1+0.1);
hl("#hl1", s1+0.25);
tl.fromTo("#axes", {opacity:0}, {opacity:1, duration:1.1, ease:"power2.out", immediateRender:false}, s1+1.3);
tl.fromTo("#ticks", {opacity:0}, {opacity:1, duration:0.9, immediateRender:false}, s1+1.9);
tl.fromTo("#curve", {strokeDashoffset:TL.len}, {strokeDashoffset:0, duration:2.8, ease:"power2.inOut", immediateRender:false}, s1+1.6);
tl.fromTo("#curve-halo", {strokeDashoffset:TL.len, opacity:0},
          {strokeDashoffset:0, opacity:.5, duration:2.8, ease:"power2.inOut", immediateRender:false}, s1+1.7);
tl.fromTo("#grid", {opacity:0}, {opacity:1, duration:1.6, immediateRender:false}, s1+3.4);

/* s2 建立：给定义、给量纲 */
const s2 = S.s2[0];
hl("#hl2", s2-0.1);
bd("#bd2", s2+0.9);

/* s3 关键动作：游标沿曲线走，读数跟着变 */
const s3 = S.s3[0];
hl("#hl3", s3-0.1);
tl.fromTo("#readout", {opacity:0, y:14}, {opacity:1, y:0, duration:0.7, immediateRender:false}, s3+0.3);
tl.fromTo(".pt[data-name='A']", {opacity:0, scale:.6}, {opacity:1, scale:1, duration:0.5, ease:"back.out(2)", immediateRender:false}, s3+1.1);
tl.fromTo("#cursorG", {opacity:0}, {opacity:1, duration:0.4, immediateRender:false}, s3+1.5);
const abT0 = s3 + 2.0, abT1 = s3 + 7.0;
TL.path.forEach((p, i) => cursorTo(p[0], p[1], abT0 + (abT1-abT0)*i/(TL.path.length-1)));
odo("#odoA", 0, 10, abT0, abT1-abT0);
/* 索引指向数字带里的行号，不是数值大小。
   示例：电脑 2200 在第 1 行（索引 0），2000 在第 11 行（索引 10），所以是 0→10。 */
odo("#odoB", 0, 10, abT0, abT1-abT0);
tl.fromTo(".pt[data-name='B']", {opacity:0, scale:.6}, {opacity:1, scale:1, duration:0.5, ease:"back.out(2)", immediateRender:false}, abT1-0.15);
dl("#dl3", abT1+0.6);

/* s4 切线：说明这一点的代价，长度别超出画布 */
const s4 = S.s4[0];
hl("#hl4", s4-0.1);
tl.fromTo("#tan", {opacity:0}, {opacity:1, duration:0.5, immediateRender:false}, s4+1.3);
tl.set("#tan", {attr:{x1:TL.tan[0], y1:TL.tan[1], x2:TL.tan[2], y2:TL.tan[3]}}, s4+1.3);
tl.to(["#cardA"], {opacity:1, duration:0.7}, s4+2.2);

/* s5 收口：图形退场，只留几个词 */
const s5 = S.s5[0];
tl.to("#left", {opacity:0, duration:0.7}, s5+0.1);
tl.to("#art", {opacity:0, duration:0.9}, s5+0.2);
tl.to("#cardA", {opacity:0, duration:0.5}, s5+0.2);
tl.fromTo("#words span", {opacity:0, y:22}, {opacity:1, y:0, duration:0.55, stagger:0.16, ease:"power2.out", immediateRender:false}, s5+1.2);
tl.to("#words", {opacity:.35, duration:0.8}, s5+3.6);
tl.fromTo("#endTitle", {opacity:0, y:16}, {opacity:1, y:0, duration:0.9, immediateRender:false}, s5+3.6);

window.__timelines = window.__timelines || {};
window.__timelines["main"] = tl;
</script>
</body>
</html>
