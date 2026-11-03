// Build the one-page slide of the box subdivision as a .pptx, from the layout of
// presentation/one-pager.html (1920 x 1080 px canvas = 13.333 x 7.5 in).
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.SKILL + "/scripts/apply_theme.js");

const MEDIA = process.argv[2];
const OUT = process.argv[3];

const THEME = {
  name: "Box subdivision",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0E1116", lt1: "E8E6E1", dk2: "161B22", lt2: "A9B1BB",
    accent1: "FF9A3C", accent2: "7FC4E8", accent3: "5FD38D", accent4: "FF7A6B",
    accent5: "F2D06B", accent6: "7F8994", hlink: "7FC4E8", folHlink: "A9B1BB",
  },
};
const HEX = {
  bg: "0E1116", card: "161B22", border: "2A313B", ink: "E8E6E1", soft: "A9B1BB",
  faint: "7F8994", orange: "FF9A3C", blue: "7FC4E8", green: "5FD38D", red: "FF7A6B",
};

const inch = (px) => px / 144;
const pt = (px) => px / 2;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "Box subdivision on one page";
pres.author = "Simone Coniglio";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const slide = pres.addSlide();
slide.background = { color: HEX.bg };

function text(runs, x, y, w, h, opts) {
  slide.addText(runs, {
    x: inch(x), y: inch(y), w: inch(w), h: inch(h), margin: 0, valign: "top",
    isTextBox: true, fontFace: "Calibri", color: HEX.soft, ...opts,
  });
}
function image(file, x, y, w, h, alt, name) {
  slide.addImage({
    path: path.join(MEDIA, file), x: inch(x), y: inch(y), w: inch(w), h: inch(h),
    altText: alt, objectName: name,
  });
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: inch(x), y: inch(y), w: inch(w), h: inch(h), rectRadius: 0.06,
    fill: { type: "none" }, line: { color: HEX.border, width: 0.75 }, objectName: name + " frame",
  });
}

// Header
text("Box subdivision", 128, 60, 600, 90, {
  fontFace: "Cambria", fontSize: pt(72), color: HEX.ink, objectName: "Title",
});
text("Choosing where to look in a multimodal landscape, one local solve at a time", 650, 96, 1142, 44, {
  fontSize: pt(32), objectName: "Subtitle",
});

// Four steps, each with its animation
const steps = [
  ["1 · Which box?", "boxes.gif",
    "Styblinski-Tang in one variable cut into ten boxes; the solver runs inside each box and each box becomes one value",
    [{ text: "Cut each axis into intervals; solve inside one box at a time. Boxes multiply, switches add." }]],
  ["2 · A value and a slope", "multipliers.gif",
    "Box 6: the solution presses on its right wall with multiplier 12.4; box 8: interior solution, multiplier zero",
    [{ text: "Pressed on a wall, the multiplier " }, { text: "λ", options: { color: HEX.red } },
      { text: " says how fast the value drops beyond it." }]],
  ["3 · Cuts steer the master", "cuts.gif",
    "Each solved box draws a cut line; the master picks the box with the lowest bound: boxes 6, 10, 9, 8, then stops at minus 25.03",
    [{ text: "Value + slope = a " }, { text: "cut", options: { color: HEX.blue } },
      { text: ". Solve the box with the lowest bound; stop when none can beat the best." }]],
  ["4 · Keep the cuts honest", "kappa.gif",
    "Box 2 holds minus 39.17; lowering every cut by kappa equals 60 lets the master continue and find it",
    [{ text: "Non-convex cuts lie. Lower them by " }, { text: "κ", options: { color: HEX.blue } },
      { text: ", or sweep κ over parallel probes." }]],
];
steps.forEach(([title, gif, alt, body], k) => {
  const x = 128 + k * 422;
  text(title, x, 168, 398, 40, { fontSize: pt(30), bold: true, color: HEX.orange, objectName: `Step ${k + 1} title` });
  image(gif, x, 214, 398, 224, alt, `Step ${k + 1} animation`);
  text(body, x, 450, 398, 110, { fontSize: pt(26), lineSpacingMultiple: 1.05, objectName: `Step ${k + 1} text` });
});

// A real run
image("run.gif", 128, 570, 560, 315,
  "Rastrigin 2D, 100 boxes: an initial design of four boxes, then rounds of four probes along the row and column of the best box plus one jump",
  "Real run animation");
text([
  { text: "A real run", options: { bold: true, color: HEX.ink } },
  { text: ", Rastrigin 2D, default settings, 4 probes per round: " },
  { text: "0", options: { color: HEX.green } },
  { text: " after 154 evaluations, 20 of 100 boxes." },
], 728, 572, 1064, 72, { fontSize: pt(28), objectName: "Real run text" });

// Headline numbers
const tiles = [
  [[{ text: "82.1" }], "bracket compliance, vs 84.0 for MMA"],
  [[{ text: "789" }], "evaluations vs 2,340 for multistart (5D)"],
  [[{ text: "10" }, { text: "5", options: { superscript: true } }, { text: " boxes" }], "on 50 switches: Rastrigin 5D solved"],
];
tiles.forEach(([num, label], k) => {
  const x = 728 + k * 361.5;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: inch(x), y: inch(657), w: inch(341), h: inch(168), rectRadius: 0.08,
    fill: { color: HEX.card }, line: { type: "none" }, objectName: `Result ${k + 1} card`,
  });
  text(num, x + 24, 672, 293, 66, { fontFace: "Cambria", fontSize: pt(58), color: HEX.orange, objectName: `Result ${k + 1} number` });
  text(label, x + 24, 744, 293, 70, { fontSize: pt(26), objectName: `Result ${k + 1} label` });
});

text("It wins when the grid separates the valleys, and loses when it doesn’t.", 728, 843, 1064, 48, {
  fontFace: "Cambria", fontSize: pt(34), color: HEX.ink, objectName: "Conclusion",
});
text("gemseo-box-subdivision  ·  pip install gemseo-box-subdivision  ·  simoneconiglio.github.io/gemseo-box-subdivision",
  128, 998, 1664, 32, { fontSize: pt(24), color: HEX.faint, objectName: "Footer" });

slide.addNotes(
  "One idea: let each local solve tell the optimizer where to look next. " +
  "1. A local solver only finds the valley it starts in, so turn “where should I start?” into “which box?”: cut each axis into intervals and solve inside one box at a time. A box is named by one row of switches per axis; boxes multiply with the dimension, switches add up: 100 000 boxes in five variables are only 50 switches. " +
  "2. Each solve gives a value and, for free, a slope: when the solution presses on a wall of its box, the Lagrange multiplier of that wall says how fast the value would drop if the wall moved. " +
  "3. Value plus slope draws a line of predictions through the other boxes, a cut. The master solves the box whose bound is lowest and stops when no bound can beat the best value: outer approximation. " +
  "4. On a non-convex landscape cuts lie and the master stops confidently at the wrong answer. Lower each cut by kappa away from its own box; too small still lies, too large enumerates, so the adaptive repair corrects only what the data contradict, and the sweep runs a ladder of kappa over the parallel probes, with nothing to tune. " +
  "Bottom left, a real run with default settings: zero after 154 evaluations, 20 boxes of 100. " +
  "Results: compliance 82.1 on the 108-variable bracket against 84.0 for MMA; 789 evaluations on Styblinski-Tang 5D against 2,340 for multistart; Rastrigin 5D solved with 100 000 boxes, which no baseline reached. " +
  "It wins when the grid separates the valleys and loses when it doesn’t: on Ackley CMA-ES wins, Griewank defeats everyone."
);

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
