import { useState, useEffect, useRef } from "react";
import type { TournamentData, MatchPrediction, KnockoutRound } from "./data/types";
import { allTournaments } from "./data/defaultData";
import trophyPng from "./imports/_Pngtree_football_world_cup_golden_trophy_8792922.png";

// ── Year themes ────────────────────────────────────────────────────────────

interface YearTheme {
  headerBg: string;          // CSS background (gradient or solid)
  headerBorder: string;
  titleColor: string;
  subtitleColor: string;
  metaColor: string;
  accentColor: string;       // pulse dot, active stage text
  gold: string;
  goldDark: string;
  globeFill: string;
  hostLabel: string;
  selectArrowColor: string;  // hex for the chevron in URL-encoded SVG
  contentBg: string;         // scrollable area background
  titleFont: string;         // CSS font-family for the "FIFA World Cup" title + year dropdown
}

const YEAR_THEMES: Record<number, YearTheme> = {
  2026: {
    headerBg: "linear-gradient(135deg, #0a1628 0%, #0d2240 50%, #152d55 100%)",
    headerBorder: "#1e3a6e",
    titleColor: "#ffffff",
    subtitleColor: "rgba(255,255,255,0.55)",
    metaColor: "rgba(255,255,255,0.45)",
    accentColor: "#4ade80",
    gold: "#f0c040",
    goldDark: "#b8860b",
    globeFill: "#1a4a2e",
    hostLabel: "USA · Canada · Mexico",
    selectArrowColor: "%23ffffff",
    contentBg: "linear-gradient(180deg, #0d1e3a 0%, #0f2347 40%, #132d58 100%)",
    titleFont: "'Anton', 'Inter', sans-serif",
  },
  2022: {
    headerBg: "linear-gradient(135deg, #3d0516 0%, #5c0a22 50%, #720d2a 100%)",
    headerBorder: "#8b1a3a",
    titleColor: "#ffffff",
    subtitleColor: "rgba(255,255,255,0.55)",
    metaColor: "rgba(255,255,255,0.45)",
    accentColor: "#fcd34d",
    gold: "#d4a843",
    goldDark: "#9a7020",
    globeFill: "#1a3d28",
    hostLabel: "Qatar",
    selectArrowColor: "%23ffffff",
    contentBg: "linear-gradient(180deg, #3a0412 0%, #50091e 40%, #620b26 100%)",
    titleFont: "'Changa', 'Inter', sans-serif",
  },
  2018: {
    headerBg: "linear-gradient(135deg, #0c1f6b 0%, #0f2680 50%, #152e99 100%)",
    headerBorder: "#1d3ba8",
    titleColor: "#ffffff",
    subtitleColor: "rgba(255,255,255,0.55)",
    metaColor: "rgba(255,255,255,0.45)",
    accentColor: "#f87171",
    gold: "#e8c44a",
    goldDark: "#a0841a",
    globeFill: "#1a3d28",
    hostLabel: "Russia",
    selectArrowColor: "%23ffffff",
    contentBg: "linear-gradient(180deg, #0b1d62 0%, #0e2478 40%, #132b90 100%)",
    titleFont: "'Russo One', 'Inter', sans-serif",
  },
};


// ── Stage ordering ─────────────────────────────────────────────────────────
// GR1/GR2/GR3 = Group Round 1/2/3. KO rounds use their shortName.

function buildStageOrder(data: TournamentData): string[] {
  return ["GR1", "GR2", "GR3", ...data.knockoutRounds.map((r) => r.shortName)];
}

function stageIndex(stage: string, order: string[]): number {
  return order.indexOf(stage);
}

// A match is shown as a prediction (dashed) if:
//   its stage comes at or after the selected stage, OR it hasn't been played yet.
function isPredictionCard(matchStage: string, selectedStage: string, played: boolean, order: string[]) {
  const atOrAfter = stageIndex(matchStage, order) >= stageIndex(selectedStage, order);
  return atOrAfter || !played;
}

// ── helpers ────────────────────────────────────────────────────────────────

// Country code → FlagCDN code (handles FIFA sub-national teams)
const FLAG_OVERRIDES: Record<string, string> = {
  "GB":      "gb-eng",   // England
  "GB-WLS":  "gb-wls",   // Wales
  "GB-SCT":  "gb-sct",   // Scotland
  "GB-NIR":  "gb-nir",   // Northern Ireland
};

function cdnCode(code: string): string {
  return (FLAG_OVERRIDES[code] ?? code).toLowerCase();
}

type FlagSize = "sm" | "md" | "lg";

function FlagIcon({ code, size = "md" }: { code: string; size?: FlagSize }) {
  if (!code) return <span className="inline-block w-6 h-4 rounded bg-gray-200" />;
  const dim: Record<FlagSize, { w: number; h: number; cdn: number }> = {
    sm: { w: 20, h: 14, cdn: 20 },
    md: { w: 28, h: 20, cdn: 40 },
    lg: { w: 36, h: 26, cdn: 40 },
  };
  const { w, h, cdn } = dim[size];
  return (
    <img
      src={`https://flagcdn.com/w${cdn}/${cdnCode(code)}.png`}
      width={w}
      height={h}
      alt={code}
      style={{
        borderRadius: 4,
        objectFit: "cover",
        display: "block",
        flexShrink: 0,
        boxShadow: "0 0 0 1px rgba(0,0,0,0.10)",
      }}
      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
    />
  );
}

function pct(v: number): string {
  return Math.round(v * 100) + "%";
}

function predictedWinner(m: MatchPrediction) {
  return m.prob1 >= m.prob2
    ? { name: m.team1.name, code: m.team1.code }
    : { name: m.team2.name, code: m.team2.code };
}

function actualWinner(m: MatchPrediction) {
  if (!m.result) return null;
  if (m.result.score1 > m.result.score2) return { name: m.team1.name, code: m.team1.code };
  if (m.result.score2 > m.result.score1) return { name: m.team2.name, code: m.team2.code };
  return { name: "Draw", code: "" };
}

// ── Group-stage match card (Google FIFA style, horizontal) ─────────────────

function GroupMatchCard({
  match,
  groupName,
  asPrediction,
  accentColor,
}: {
  match: MatchPrediction;
  groupName: string;
  asPrediction: boolean;
  accentColor: string;
}) {
  const isPlayedResult = !asPrediction && !!match.played && !!match.result;
  const higher1 = match.prob1 >= match.prob2;

  const w = isPlayedResult ? actualWinner(match) : predictedWinner(match);

  const res1 = match.result?.score1;
  const res2 = match.result?.score2;
  const actualWin1 = isPlayedResult && res1 !== undefined && res2 !== undefined && res1 > res2;
  const actualWin2 = isPlayedResult && res1 !== undefined && res2 !== undefined && res2 > res1;

  // Predictions are the whole point of a predictor simulation, so they get
  // the bold, eye-catching treatment (full opacity, thicker accent-colored
  // border, wider glow); real results are historical record-keeping and
  // recede — flat border, no glow, slightly faded.
  const cardStyle = asPrediction
    ? { border: `2px solid ${accentColor}`, boxShadow: `0 0 0 3px ${accentColor}33, 0 4px 16px ${accentColor}40` }
    : { border: "1px solid rgba(255,255,255,0.10)", boxShadow: "none", opacity: 0.75 };

  return (
    <div
      className="bg-white rounded-xl overflow-hidden transition-all"
      style={cardStyle}
    >
      {/* Group label */}
      <div className="px-3 pt-2.5 pb-1">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          {groupName}
        </span>
      </div>

      <div className="flex items-stretch pb-3 px-1">
        {/* Left: team rows */}
        <div className="flex-1 px-2 space-y-2">
          {/* Team 1 */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <FlagIcon code={match.team1.code} size="md" />
              <span
                className={`text-sm font-medium truncate ${
                  isPlayedResult && !actualWin1 ? "text-gray-400" : "text-gray-800"
                }`}
              >
                {match.team1.name}
              </span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {isPlayedResult ? (
                <>
                  <span className={`text-sm font-bold ${actualWin1 ? "text-gray-900" : "text-gray-400"}`}>
                    {res1}
                  </span>
                  {actualWin1 && <span className="text-gray-500 text-xs leading-none">◄</span>}
                </>
              ) : (
                <>
                  <span className={`font-mono text-sm font-semibold ${higher1 ? "text-emerald-600" : "text-gray-400"}`}>
                    {pct(match.prob1)}
                  </span>
                  {higher1 && <span className="text-emerald-500 text-xs leading-none">◄</span>}
                </>
              )}
            </div>
          </div>

          {/* Team 2 */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <FlagIcon code={match.team2.code} size="md" />
              <span
                className={`text-sm font-medium truncate ${
                  isPlayedResult && !actualWin2 ? "text-gray-400" : "text-gray-800"
                }`}
              >
                {match.team2.name}
              </span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {isPlayedResult ? (
                <>
                  <span className={`text-sm font-bold ${actualWin2 ? "text-gray-900" : "text-gray-400"}`}>
                    {res2}
                  </span>
                  {actualWin2 && <span className="text-gray-500 text-xs leading-none">◄</span>}
                </>
              ) : (
                <>
                  <span className={`font-mono text-sm font-semibold ${!higher1 ? "text-emerald-600" : "text-gray-400"}`}>
                    {pct(match.prob2)}
                  </span>
                  {!higher1 && <span className="text-emerald-500 text-xs leading-none">◄</span>}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Vertical divider */}
        <div className="w-px bg-gray-100 mx-1 self-stretch" />

        {/* Right: status + winner */}
        <div className="w-[72px] flex flex-col items-center justify-center py-1 px-1 gap-1 flex-shrink-0">
          {isPlayedResult ? (
            <>
              <span className="text-xs font-bold text-gray-500 tracking-wide">FT</span>
              {match.date && (
                <span className="text-xs text-gray-400 leading-none">{match.date}</span>
              )}
              <div className="text-center mt-0.5">
                {w && w.code ? (
                  <>
                    <div className="flex justify-center"><FlagIcon code={w.code} size="md" /></div>
                    <div className="text-xs font-semibold text-gray-600 leading-tight mt-1 text-center max-w-full truncate">
                      {w.name.split(" ")[0]}
                    </div>
                  </>
                ) : (
                  <div className="text-xs font-semibold text-gray-400">Draw</div>
                )}
              </div>
            </>
          ) : (
            <div className="text-center">
              {w && (
                <>
                  <div className="flex justify-center"><FlagIcon code={w.code} size="md" /></div>
                  <div className="text-xs font-semibold text-gray-600 leading-tight mt-1 max-w-full truncate">
                    {w.name.split(" ")[0]}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Compact match card for the knockout bracket ────────────────────────────

function BracketMatchCard({
  match,
  asPrediction,
  accentColor,
}: {
  match: MatchPrediction;
  asPrediction: boolean;
  accentColor: string;
}) {
  const isPlayedResult = !asPrediction && !!match.played && !!match.result;
  const higher1 = match.prob1 >= match.prob2;
  const w = isPlayedResult ? actualWinner(match) : predictedWinner(match);
  const res1 = match.result?.score1;
  const res2 = match.result?.score2;
  const actualWin1 = isPlayedResult && res1 !== undefined && res2 !== undefined && res1 > res2;
  const actualWin2 = isPlayedResult && res1 !== undefined && res2 !== undefined && res2 > res1;

  // Predictions are the whole point of a predictor simulation, so they get
  // the bold, eye-catching treatment (full opacity, thicker accent-colored
  // border, wider glow); real results are historical record-keeping and
  // recede — flat border, no glow, slightly faded.
  const cardStyle = asPrediction
    ? { border: `2px solid ${accentColor}`, boxShadow: `0 0 0 3px ${accentColor}33, 0 4px 16px ${accentColor}40` }
    : { border: "1px solid rgba(255,255,255,0.10)", boxShadow: "none", opacity: 0.75 };

  return (
    <div
      className="bg-white rounded-xl overflow-hidden w-44 flex-shrink-0 transition-all"
      style={cardStyle}
    >
      {/* Teams */}
      <div className="flex px-0 pt-1">
        {/* Left: team rows */}
        <div className="flex-1 px-2.5 py-1.5 space-y-1.5">
          <div className="flex items-center justify-between gap-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <FlagIcon code={match.team1.code} size="sm" />
              <span className={`text-xs font-medium truncate ${isPlayedResult && !actualWin1 ? "text-gray-400" : "text-gray-800"}`}>
                {match.team1.name}
              </span>
            </div>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              {isPlayedResult ? (
                <>
                  <span className={`text-xs font-bold ${actualWin1 ? "text-gray-900" : "text-gray-400"}`}>{res1}</span>
                  {actualWin1 && <span className="text-gray-400 text-xs">◄</span>}
                </>
              ) : (
                <>
                  <span className={`font-mono text-xs font-semibold ${higher1 ? "text-emerald-600" : "text-gray-400"}`}>{pct(match.prob1)}</span>
                  {higher1 && <span className="text-emerald-500 text-xs">◄</span>}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center justify-between gap-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <FlagIcon code={match.team2.code} size="sm" />
              <span className={`text-xs font-medium truncate ${isPlayedResult && !actualWin2 ? "text-gray-400" : "text-gray-800"}`}>
                {match.team2.name}
              </span>
            </div>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              {isPlayedResult ? (
                <>
                  <span className={`text-xs font-bold ${actualWin2 ? "text-gray-900" : "text-gray-400"}`}>{res2}</span>
                  {actualWin2 && <span className="text-gray-400 text-xs">◄</span>}
                </>
              ) : (
                <>
                  <span className={`font-mono text-xs font-semibold ${!higher1 ? "text-emerald-600" : "text-gray-400"}`}>{pct(match.prob2)}</span>
                  {!higher1 && <span className="text-emerald-500 text-xs">◄</span>}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="w-px bg-gray-100 self-stretch" />

        {/* Right: winner */}
        <div className="w-10 flex flex-col items-center justify-center py-1 px-1 flex-shrink-0">
          {w && (
            <div className="text-center">
              <FlagIcon code={w.code || ""} size="sm" />
              {isPlayedResult && (
                <div className="text-xs font-bold text-gray-500 mt-0.5 leading-none">FT</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── GroupRoundView ─────────────────────────────────────────────────────────
// Shows all matches for a given matchday (1, 2, or 3) across all groups.

function GroupRoundView({
  data,
  matchday,
  selectedStage,
  stageOrder,
  accentColor,
}: {
  data: TournamentData;
  matchday: 1 | 2 | 3;
  selectedStage: string;
  stageOrder: string[];
  accentColor: string;
}) {
  const matchStage = matchday === 1 ? "GR1" : matchday === 2 ? "GR2" : "GR3";
  // Gather matches: indices 0-1 = matchday 1, 2-3 = matchday 2, 4-5 = matchday 3
  const offset = (matchday - 1) * 2;
  const matchPairs: { match: MatchPrediction; groupName: string }[] = [];
  for (const group of data.groups) {
    for (let i = offset; i < offset + 2; i++) {
      if (group.matches[i]) {
        matchPairs.push({ match: group.matches[i], groupName: group.name });
      }
    }
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {matchPairs.map(({ match, groupName }) => {
        const pred = isPredictionCard(matchStage, selectedStage, !!match.played, stageOrder);
        return (
          <GroupMatchCard
            key={match.id}
            match={match}
            groupName={groupName}
            asPrediction={pred}
            accentColor={accentColor}
          />
        );
      })}
    </div>
  );
}

// ── Bracket layout constants ───────────────────────────────────────────────

const CARD_H = 82;
const LABEL_H = 28;
const BASE_GAP = 8;
const CONN_W = 22;

function gapFor(roundIdx: number) {
  return (CARD_H + BASE_GAP) * Math.pow(2, roundIdx) - CARD_H;
}
function topMarginFor(roundIdx: number) {
  return gapFor(roundIdx) / 2;
}

// ── BracketHalfColumn ──────────────────────────────────────────────────────

function BracketHalfColumn({
  round,
  roundIdx,
  highlighted,
  selectedStage,
  stageOrder,
  accentColor,
}: {
  round: { shortName: string; matches: MatchPrediction[] };
  roundIdx: number;
  highlighted: boolean;
  selectedStage: string;
  stageOrder: string[];
  accentColor: string;
}) {
  const g = gapFor(roundIdx);
  const tm = topMarginFor(roundIdx);

  return (
    <div
      className="flex flex-col flex-shrink-0 rounded-xl transition-colors"
      style={{
        paddingLeft: 6, paddingRight: 6,
        ...(highlighted ? { background: `${accentColor}12`, outline: `1px solid ${accentColor}40` } : {}),
      }}
    >
      <div className="flex items-center justify-center" style={{ height: LABEL_H }}>
        <span className="text-xs font-bold uppercase tracking-widest" style={{ color: highlighted ? accentColor : "rgba(255,255,255,0.4)" }}>
          {round.shortName}
        </span>
      </div>
      {round.matches.map((match, i) => {
        const pred = isPredictionCard(round.shortName, selectedStage, !!match.played, stageOrder);
        return (
          <div key={match.id} style={{ marginTop: i === 0 ? tm : g }}>
            <BracketMatchCard match={match} asPrediction={pred} accentColor={accentColor} />
          </div>
        );
      })}
    </div>
  );
}

// ── BracketConnector (SVG) ─────────────────────────────────────────────────

function BracketConnector({
  outerRoundIdx,
  outerMatchCount,
  totalH,
  fromRight = false,
}: {
  outerRoundIdx: number;
  outerMatchCount: number;
  totalH: number;
  fromRight?: boolean;
}) {
  const g = gapFor(outerRoundIdx);
  const tm = topMarginFor(outerRoundIdx);
  const pairs = outerMatchCount / 2;
  const color = "#e5e7eb";
  const w = CONN_W;
  const lines: React.ReactNode[] = [];

  for (let p = 0; p < pairs; p++) {
    const y1 = LABEL_H + tm + (2 * p) * (CARD_H + g) + CARD_H / 2;
    const y2 = LABEL_H + tm + (2 * p + 1) * (CARD_H + g) + CARD_H / 2;
    const ym = (y1 + y2) / 2;

    if (!fromRight) {
      lines.push(
        <g key={p} stroke={color} strokeWidth={1.5} fill="none">
          <line x1={0} y1={y1} x2={w / 2} y2={y1} />
          <line x1={0} y1={y2} x2={w / 2} y2={y2} />
          <line x1={w / 2} y1={y1} x2={w / 2} y2={y2} />
          <line x1={w / 2} y1={ym} x2={w} y2={ym} />
        </g>
      );
    } else {
      lines.push(
        <g key={p} stroke={color} strokeWidth={1.5} fill="none">
          <line x1={w} y1={y1} x2={w / 2} y2={y1} />
          <line x1={w} y1={y2} x2={w / 2} y2={y2} />
          <line x1={w / 2} y1={y1} x2={w / 2} y2={y2} />
          <line x1={w / 2} y1={ym} x2={0} y2={ym} />
        </g>
      );
    }
  }

  return (
    <svg width={w} height={totalH} style={{ flexShrink: 0, display: "block", overflow: "visible" }}>
      {lines}
    </svg>
  );
}

function FinalConnector({ totalH }: { totalH: number }) {
  return (
    <svg width={CONN_W + 4} height={totalH} style={{ flexShrink: 0, display: "block", overflow: "visible" }}>
      <line x1={0} y1={totalH / 2} x2={CONN_W + 4} y2={totalH / 2} stroke="#e5e7eb" strokeWidth={1.5} />
    </svg>
  );
}

// ── SymmetricBracket ───────────────────────────────────────────────────────

function SymmetricBracket({
  knockoutRounds,
  activeRoundName,
  selectedStage,
  stageOrder,
  accentColor,
}: {
  knockoutRounds: KnockoutRound[];
  activeRoundName?: string;
  selectedStage: string;
  stageOrder: string[];
  accentColor: string;
}) {
  if (knockoutRounds.length < 2) return null;

  const finalRound = knockoutRounds[knockoutRounds.length - 1];
  const mainRounds = knockoutRounds.slice(0, -1);

  const leftRounds = mainRounds.map((r) => ({
    ...r,
    matches: r.matches.slice(0, Math.floor(r.matches.length / 2)),
  }));
  const rightRounds = [...mainRounds].reverse().map((r) => ({
    ...r,
    matches: r.matches.slice(Math.floor(r.matches.length / 2)),
  }));

  const N = leftRounds[0]?.matches.length ?? 1;
  const totalCardAreaH = N * (CARD_H + BASE_GAP);
  const totalH = LABEL_H + totalCardAreaH;
  const finalCardMarginTop = totalCardAreaH / 2 - CARD_H / 2;
  const isFinalHighlighted = activeRoundName === finalRound.shortName;
  const finalPred = isPredictionCard(
    finalRound.shortName,
    selectedStage,
    !!finalRound.matches[0]?.played,
    stageOrder
  );

  return (
    <div className="overflow-x-auto">
      <div className="inline-flex items-start" style={{ minHeight: totalH, padding: "12px 16px" }}>
        {/* Left half */}
        {leftRounds.map((round, ri) => (
          <div key={round.shortName + "-L"} className="flex items-start">
            <BracketHalfColumn
              round={round}
              roundIdx={ri}
              highlighted={activeRoundName === round.shortName}
              selectedStage={selectedStage}
              stageOrder={stageOrder}
              accentColor={accentColor}
            />
            {ri < leftRounds.length - 1 ? (
              <BracketConnector
                outerRoundIdx={ri}
                outerMatchCount={leftRounds[ri].matches.length}
                totalH={totalH}
                fromRight={false}
              />
            ) : (
              <FinalConnector totalH={totalH} />
            )}
          </div>
        ))}

        {/* Final */}
        <div
          className="flex flex-col flex-shrink-0 rounded-xl transition-colors"
          style={{
            paddingLeft: 6, paddingRight: 6,
            ...(isFinalHighlighted ? { background: `${accentColor}12`, outline: `1px solid ${accentColor}40` } : {}),
          }}
        >
          <div className="flex items-center justify-center" style={{ height: LABEL_H }}>
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: isFinalHighlighted ? accentColor : "rgba(255,255,255,0.4)" }}>
              Final
            </span>
          </div>
          <div style={{ marginTop: finalCardMarginTop }}>
            <BracketMatchCard match={finalRound.matches[0]} asPrediction={finalPred} accentColor={accentColor} />
          </div>
        </div>

        {/* Right half */}
        {rightRounds.map((round, ri) => {
          const roundIdx = rightRounds.length - 1 - ri;
          const outerMatchCount = rightRounds[ri + 1]?.matches.length ?? round.matches.length;
          const outerRoundIdx = rightRounds.length - 1 - (ri + 1);

          return (
            <div key={round.shortName + "-R"} className="flex items-start">
              {ri === 0 ? (
                <FinalConnector totalH={totalH} />
              ) : (
                <BracketConnector
                  outerRoundIdx={outerRoundIdx < 0 ? 0 : outerRoundIdx}
                  outerMatchCount={outerMatchCount}
                  totalH={totalH}
                  fromRight={true}
                />
              )}
              <BracketHalfColumn
                round={round}
                roundIdx={roundIdx}
                highlighted={activeRoundName === round.shortName}
                selectedStage={selectedStage}
                stageOrder={stageOrder}
                accentColor={accentColor}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────

const YEARS = [2026, 2022, 2018];

export default function App() {
  const [selectedYear, setSelectedYear] = useState<number>(2026);
  const [data, setData] = useState<TournamentData>(allTournaments[2026]);
  // The active stage is either "GR1"/"GR2"/"GR3" or a knockout shortName
  const [activeStage, setActiveStage] = useState<string>("GR2");
  const [viewMatchday, setViewMatchday] = useState<1 | 2 | 3>(2); // which group round to display
  const [_viewKOround, setViewKOround] = useState<string | null>(null);

  // Raw predictions.json payload, fetched once per year — nested as
  // payload.anchors[stageName], one full set of probabilities per possible
  // anchor point (see export_predictions.py's ANCHOR_STAGES). Kept in state
  // so re-selecting an anchor re-merges from already-fetched data instead
  // of re-fetching the file over the network every time the slider moves.
  const [predictionsPayload, setPredictionsPayload] = useState<any>(null);

  const groupSectionRef = useRef<HTMLDivElement>(null);
  const bracketSectionRef = useRef<HTMLDivElement>(null);

  const stageOrder = buildStageOrder(data);
  const isGroupStage = activeStage.startsWith("GR");
  const isKOStage = !isGroupStage;
  const theme = YEAR_THEMES[selectedYear] ?? YEAR_THEMES[2026];

  // Fetch the raw overlay once per year — does NOT merge into `data` here,
  // since the merge depends on activeStage too (see the effect below).
  useEffect(() => {
    fetch("/predictions.json")
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((payload) => setPredictionsPayload(payload))
      .catch(() => setPredictionsPayload(null));
  }, [selectedYear]);

  // Re-merge whenever EITHER the fetched payload OR the selected anchor
  // stage changes — this is what makes moving the anchor slider actually
  // change probabilities for a given match, instead of only changing which
  // matches are styled as "prediction" vs "result" cards. Every match at
  // every anchor was precomputed server-side (predict_match_asof re-run
  // per anchor cutoff), so this is a pure client-side re-selection, not a
  // recomputation — moving the slider is instant.
  useEffect(() => {
    const base = allTournaments[selectedYear];
    if (!base) return;
    // predictions.json only ever covers the live 2026 tournament — for any
    // other selected year, show that year's plain static data with no
    // overlay merge. Without this check, a 2022/2018 selection would get
    // silently overwritten back to 2026 the next time this effect re-ran
    // (e.g. from any anchor-stage interaction), since the overlay's own
    // year never matches — which is exactly why those years looked
    // unselectable.
    if (!predictionsPayload || predictionsPayload.year !== selectedYear) {
      setData(base);
      return;
    }
    const payload = predictionsPayload.anchors?.[activeStage] ?? predictionsPayload;
    const merged: TournamentData = {
      ...base,
      groups: base.groups.map((g) => {
        const pg = payload.groups?.[g.id];
        if (!pg) return g;
        return {
          ...g,
          teams: g.teams.map((ts, i) => ({ ...ts, ...(pg.teams?.[i] ?? {}) })),
          matches: g.matches.map((m, i) => ({ ...m, ...(pg.matches?.[i] ?? {}) })),
        };
      }),
      knockoutRounds: base.knockoutRounds.map((r) => {
        const pr = payload.knockoutRounds?.[r.shortName];
        if (!pr) return r;
        return { ...r, matches: r.matches.map((m, i) => ({ ...m, ...(pr[i] ?? {}) })) };
      }),
    };
    setData(merged);
  }, [predictionsPayload, activeStage, selectedYear]);

  function handleYearChange(y: number) {
    setSelectedYear(y);
    setData(allTournaments[y]);
    setActiveStage("GR1");
    setViewMatchday(1);
    setViewKOround(null);
  }

  function handleGroupRoundSelect(matchday: 1 | 2 | 3) {
    const stageId = `GR${matchday}` as string;
    setActiveStage(stageId);
    setViewMatchday(matchday);
    setViewKOround(null);
    setTimeout(() => groupSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  function handleKnockoutSelect(shortName: string) {
    setActiveStage(shortName);
    setViewKOround(shortName);
    setTimeout(() => bracketSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  const numGroupRounds = 3; // always 3 matchdays in group stage

  return (
    <div className="min-h-screen transition-all duration-500" style={{ background: theme.contentBg, fontFamily: "'Inter', 'Helvetica Neue', sans-serif" }}>

      {/* ── Header ── */}
      <header
        className="sticky top-0 z-30 transition-all duration-500"
        style={{
          background: theme.headerBg,
          borderBottom: `1px solid ${theme.headerBorder}`,
        }}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          {/* Left: trophy + title */}
          <div className="flex items-center gap-4">
            {/* Trophy */}
            <div className="flex-shrink-0" style={{ filter: "drop-shadow(0 2px 12px rgba(0,0,0,0.5))" }}>
              <img src={trophyPng} alt="World Cup Trophy" style={{ height: 72, width: "auto", objectFit: "contain" }} />
            </div>

            {/* Title block */}
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                {/* Year dropdown embedded in title */}
                <select
                  value={selectedYear}
                  onChange={(e) => handleYearChange(Number(e.target.value))}
                  className="text-3xl bg-transparent border-0 outline-none cursor-pointer appearance-none transition-colors"
                  style={{
                    color: theme.gold,
                    paddingRight: "20px",
                    fontFamily: theme.titleFont,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='${theme.selectArrowColor}' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                    backgroundRepeat: "no-repeat",
                    backgroundPosition: "right 2px center",
                  }}
                >
                  {YEARS.map((y) => <option key={y} value={y} style={{ background: "#1a1a2e", color: "#fff", fontFamily: "'Inter', sans-serif" }}>{y}</option>)}
                </select>
                <span className="text-3xl" style={{ color: theme.titleColor, fontFamily: theme.titleFont }}>
                  FIFA World Cup
                </span>
              </div>
              <div className="flex items-center gap-3 mt-0.5">
                <span className="text-sm font-semibold tracking-wide" style={{ color: theme.subtitleColor }}>
                  Prediction Simulator
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full border font-medium"
                  style={{ color: theme.gold, borderColor: theme.gold + "55", background: theme.gold + "15" }}>
                  {theme.hostLabel}
                </span>
              </div>
              <p className="text-xs font-medium mt-1" style={{ color: theme.metaColor }}>
                {data.teamCount} Teams · {data.groups.length} Groups
              </p>
            </div>
          </div>

          {/* Right: prediction indicator */}
          <div className="flex items-center gap-2 text-xs" style={{ color: theme.metaColor }}>
            <span className="w-2 h-2 rounded-full inline-block animate-pulse" style={{ background: theme.accentColor }} />
            <span>
              Predicting from{" "}
              <strong style={{ color: theme.accentColor }}>
                {activeStage.startsWith("GR") ? `Round ${activeStage[2]}` : activeStage}
              </strong>{" "}
              onwards
            </span>
          </div>
        </div>
      </header>

      {/* ── Round Selector ── */}
      <div className="sticky top-[112px] z-20 shadow-sm transition-all duration-500" style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(12px)", borderBottom: `1px solid ${theme.headerBorder}` }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3">
          <div className="flex flex-wrap items-center gap-4">
            {/* Group stage rounds */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider whitespace-nowrap" style={{ color: "rgba(255,255,255,0.5)" }}>
                Group Stage
              </span>
              <div className="flex items-center gap-1.5">
                {Array.from({ length: numGroupRounds }, (_, i) => i + 1).map((rd) => {
                  const stageId = `GR${rd}`;
                  const isActive = activeStage === stageId;
                  return (
                    <button
                      key={rd}
                      onClick={() => handleGroupRoundSelect(rd as 1 | 2 | 3)}
                      className="text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all whitespace-nowrap"
                      style={isActive ? {
                        borderColor: theme.accentColor,
                        background: theme.accentColor + "18",
                        color: theme.accentColor === "#fcd34d" ? "#92620a" : theme.accentColor,
                        boxShadow: `0 0 0 3px ${theme.accentColor}22`,
                      } : {
                        borderColor: "rgba(255,255,255,0.18)",
                        background: "rgba(255,255,255,0.08)",
                        color: "rgba(255,255,255,0.65)",
                      }}
                    >
                      Round {rd}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="h-6 w-px hidden sm:block" style={{ background: "rgba(255,255,255,0.15)" }} />

            {/* Knockout rounds */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold uppercase tracking-wider whitespace-nowrap" style={{ color: "rgba(255,255,255,0.5)" }}>
                Knockout
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {data.knockoutRounds.map((r) => {
                  const isActive = activeStage === r.shortName;
                  return (
                    <button
                      key={r.shortName}
                      onClick={() => handleKnockoutSelect(r.shortName)}
                      className="text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all whitespace-nowrap"
                      style={isActive ? {
                        borderColor: theme.accentColor,
                        background: theme.accentColor + "18",
                        color: theme.accentColor === "#fcd34d" ? "#92620a" : theme.accentColor,
                        boxShadow: `0 0 0 3px ${theme.accentColor}22`,
                      } : {
                        borderColor: "rgba(255,255,255,0.18)",
                        background: "rgba(255,255,255,0.08)",
                        color: "rgba(255,255,255,0.65)",
                      }}
                    >
                      {r.shortName}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mt-2">
            <div className="flex items-center gap-1.5">
              <div className="w-8 h-4 rounded" style={{ border: "1px solid rgba(255,255,255,0.35)", background: "rgba(255,255,255,0.1)" }} />
              <span className="text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>Actual result</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-8 h-4 rounded" style={{ border: "2px dashed rgba(255,255,255,0.35)", background: "rgba(255,255,255,0.05)" }} />
              <span className="text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>Model prediction</span>
            </div>
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-10">

        {/* ── Group Stage Section ── */}
        <section ref={groupSectionRef}>
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-black tracking-tight" style={{ color: "rgba(255,255,255,0.95)" }}>Group Stage</h2>
            <span className="text-xs font-medium rounded-full px-2.5 py-0.5" style={{ color: "rgba(255,255,255,0.5)", background: "rgba(255,255,255,0.1)" }}>
              {data.groups.length} groups · {data.teamCount} teams
            </span>
          </div>

          {/* Round tabs for browsing */}
          <div className="flex items-center gap-2 mb-4" style={{ borderBottom: "1px solid rgba(255,255,255,0.12)" }}>
            {Array.from({ length: numGroupRounds }, (_, i) => i + 1).map((rd) => {
              const isViewing = viewMatchday === rd;
              const stageId = `GR${rd}`;
              const isSelected = activeStage === stageId;
              return (
                <button
                  key={rd}
                  onClick={() => setViewMatchday(rd as 1 | 2 | 3)}
                  className="pb-2 px-3 text-sm font-semibold border-b-2 transition-all -mb-px"
                  style={
                    isViewing
                      ? isSelected
                        ? { borderColor: theme.accentColor, color: theme.accentColor }
                        : { borderColor: "rgba(255,255,255,0.8)", color: "rgba(255,255,255,0.9)" }
                      : { borderColor: "transparent", color: "rgba(255,255,255,0.35)" }
                  }
                >
                  Round {rd}
                  {isSelected && (
                    <span className="ml-1.5 text-xs rounded-full px-1.5 py-0.5 font-bold" style={{ background: theme.accentColor + "28", color: theme.accentColor }}>
                      ★
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <GroupRoundView
            data={data}
            matchday={viewMatchday}
            selectedStage={activeStage}
            stageOrder={stageOrder}
            accentColor={theme.accentColor}
          />
        </section>

        {/* ── Knockout Bracket Section ── */}
        <section ref={bracketSectionRef}>
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-black tracking-tight" style={{ color: "rgba(255,255,255,0.95)" }}>Knockout Stage</h2>
            <span className="text-xs font-medium rounded-full px-2.5 py-0.5" style={{ color: "rgba(255,255,255,0.5)", background: "rgba(255,255,255,0.1)" }}>
              {data.knockoutRounds.length} rounds
            </span>
          </div>

          <div className="rounded-2xl overflow-hidden" style={{ background: "rgba(0,0,0,0.25)", border: `1px solid ${theme.headerBorder}` }}>
            <SymmetricBracket
              knockoutRounds={data.knockoutRounds}
              activeRoundName={isKOStage ? activeStage : undefined}
              selectedStage={activeStage}
              stageOrder={stageOrder}
              accentColor={theme.accentColor}
            />
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="mt-16 py-8" style={{ borderTop: `1px solid ${theme.headerBorder}`, background: "rgba(0,0,0,0.2)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 text-center">
          <p className="text-xs" style={{ color: "rgba(255,255,255,0.35)" }}>
            Predictions from{" "}
            <code className="font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }}>wc_predictor.py</code>
            {" "}— place{" "}
            <code className="font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }}>predictions.json</code>
            {" "}in <code className="font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }}>/public</code> to override defaults.
          </p>
        </div>
      </footer>
    </div>
  );
}
