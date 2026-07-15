import type { TournamentData, MatchPrediction } from "./types";

// ── helpers ────────────────────────────────────────────────────────────────

type Opts = { played?: boolean; s1?: number; s2?: number; date?: string };

function m(
  id: string,
  t1: [string, string],
  t2: [string, string],
  p1: number,
  pd: number,
  p2: number,
  opts: Opts = {}
): MatchPrediction {
  return {
    id,
    team1: { name: t1[0], code: t1[1] },
    team2: { name: t2[0], code: t2[1] },
    prob1: p1,
    probDraw: pd,
    prob2: p2,
    played: opts.played ?? false,
    result:
      opts.s1 !== undefined && opts.s2 !== undefined
        ? { score1: opts.s1, score2: opts.s2 }
        : undefined,
    date: opts.date,
  };
}

function ts(
  name: string,
  code: string,
  pl: number,
  w: number,
  d: number,
  l: number,
  gf: number,
  ga: number,
  pts: number,
  adv: number
) {
  return {
    team: { name, code },
    played: pl,
    won: w,
    drawn: d,
    lost: l,
    gf,
    ga,
    points: pts,
    advanceProb: adv,
  };
}

// ══════════════════════════════════════════════════════════════════════════
// 2026 — 48 teams, 12 groups of 4, Round 1 played
// Group matches: indices 0-1 = matchday 1, 2-3 = matchday 2, 4-5 = matchday 3
// ══════════════════════════════════════════════════════════════════════════

export const tournament2026: TournamentData = {
  year: 2026,
  teamCount: 48,
  groups: [
    {
      id: "A", name: "Group A",
      teams: [
        ts("Mexico", "MX", 3, 3, 0, 0, 6, 0, 9, 1.0),
        ts("South Africa", "ZA", 3, 1, 1, 1, 2, 3, 4, 1.0),
        ts("South Korea", "KR", 3, 1, 0, 2, 2, 3, 3, 0.0),
        ts("Czech Republic", "CZ", 3, 0, 1, 2, 2, 6, 1, 0.0),
      ],
      matches: [
        m("A_1_15186710", ["Mexico","MX"], ["South Africa","ZA"], 0.6999, 0, 0.3001, { played: true, s1: 2, s2: 0 }),
        m("A_1_15186720", ["South Korea","KR"], ["Czech Republic","CZ"], 0.6347, 0, 0.3653, { played: true, s1: 2, s2: 1 }),
        m("A_2_15186490", ["Mexico","MX"], ["South Korea","KR"], 0.6320, 0, 0.3680, { played: true, s1: 1, s2: 0 }),
        m("A_2_15186731", ["Czech Republic","CZ"], ["South Africa","ZA"], 0.4387, 0, 0.5613, { played: true, s1: 1, s2: 1 }),
        m("A_3_15186732", ["Czech Republic","CZ"], ["Mexico","MX"], 0.2510, 0, 0.7490, { played: true, s1: 0, s2: 3 }),
        m("A_3_15186744", ["South Africa","ZA"], ["South Korea","KR"], 0.4240, 0, 0.5760, { played: true, s1: 1, s2: 0 }),
      ],
    },
    {
      id: "B", name: "Group B",
      teams: [
        ts("Switzerland", "CH", 3, 2, 1, 0, 7, 3, 7, 1.0),
        ts("Canada", "CA", 3, 1, 1, 1, 8, 3, 4, 1.0),
        ts("Bosnia and Herzegovina", "BA", 3, 1, 1, 1, 5, 6, 4, 1.0),
        ts("Qatar", "QA", 3, 0, 1, 2, 2, 10, 1, 0.0),
      ],
      matches: [
        m("B_1_15186526", ["Qatar","QA"], ["Switzerland","CH"], 0.2198, 0, 0.7802, { played: true, s1: 1, s2: 1 }),
        m("B_1_15186836", ["Canada","CA"], ["Bosnia and Herzegovina","BA"], 0.6628, 0, 0.3372, { played: true, s1: 1, s2: 1 }),
        m("B_2_15186798", ["Canada","CA"], ["Qatar","QA"], 0.7121, 0, 0.2879, { played: true, s1: 6, s2: 0 }),
        m("B_2_15186806", ["Switzerland","CH"], ["Bosnia and Herzegovina","BA"], 0.7658, 0, 0.2342, { played: true, s1: 4, s2: 1 }),
        m("B_3_15186821", ["Switzerland","CH"], ["Canada","CA"], 0.6761, 0, 0.3239, { played: true, s1: 2, s2: 1 }),
        m("B_3_15186829", ["Bosnia and Herzegovina","BA"], ["Qatar","QA"], 0.4082, 0, 0.5918, { played: true, s1: 3, s2: 1 }),
      ],
    },
    {
      id: "C", name: "Group C",
      teams: [
        ts("Brazil", "BR", 3, 2, 1, 0, 7, 1, 7, 1.0),
        ts("Morocco", "MA", 3, 2, 1, 0, 6, 3, 7, 1.0),
        ts("Scotland", "GB", 3, 1, 0, 2, 1, 4, 3, 0.0),
        ts("Haiti", "HT", 3, 0, 0, 3, 2, 8, 0, 0.0),
      ],
      matches: [
        m("C_1_15186850", ["Brazil","BR"], ["Morocco","MA"], 0.4734, 0, 0.5266, { played: true, s1: 1, s2: 1 }),
        m("C_1_15186853", ["Haiti","HT"], ["Scotland","GB"], 0.3487, 0, 0.6513, { played: true, s1: 0, s2: 1 }),
        m("C_2_15186856", ["Brazil","BR"], ["Haiti","HT"], 0.8878, 0, 0.1122, { played: true, s1: 3, s2: 0 }),
        m("C_2_15186859", ["Scotland","GB"], ["Morocco","MA"], 0.3025, 0, 0.6975, { played: true, s1: 0, s2: 1 }),
        m("C_3_15186861", ["Scotland","GB"], ["Brazil","BR"], 0.1910, 0, 0.8090, { played: true, s1: 0, s2: 3 }),
        m("C_3_15186864", ["Morocco","MA"], ["Haiti","HT"], 0.8116, 0, 0.1884, { played: true, s1: 4, s2: 2 }),
      ],
    },
    {
      id: "D", name: "Group D",
      teams: [
        ts("USA", "US", 3, 2, 0, 1, 8, 4, 6, 1.0),
        ts("Australia", "AU", 3, 1, 1, 1, 2, 2, 4, 1.0),
        ts("Paraguay", "PY", 3, 1, 1, 1, 2, 4, 4, 1.0),
        ts("Turkey", "TR", 3, 1, 0, 2, 3, 5, 3, 0.0),
      ],
      matches: [
        m("D_1_15186873", ["USA","US"], ["Paraguay","PY"], 0.7267, 0, 0.2733, { played: true, s1: 4, s2: 1 }),
        m("D_1_15186874", ["Australia","AU"], ["Turkey","TR"], 0.6106, 0, 0.3894, { played: true, s1: 2, s2: 0 }),
        m("D_2_15186878", ["USA","US"], ["Australia","AU"], 0.5574, 0, 0.4426, { played: true, s1: 2, s2: 0 }),
        m("D_2_15186879", ["Turkey","TR"], ["Paraguay","PY"], 0.4893, 0, 0.5107, { played: true, s1: 0, s2: 1 }),
        m("D_3_15186887", ["Turkey","TR"], ["USA","US"], 0.4605, 0, 0.5395, { played: true, s1: 3, s2: 2 }),
        m("D_3_15186891", ["Paraguay","PY"], ["Australia","AU"], 0.3466, 0, 0.6534, { played: true, s1: 0, s2: 0 }),
      ],
    },
    {
      id: "E", name: "Group E",
      teams: [
        ts("Germany", "DE", 3, 2, 0, 1, 10, 4, 6, 1.0),
        ts("Ivory Coast", "CI", 3, 2, 0, 1, 4, 2, 6, 1.0),
        ts("Ecuador", "EC", 3, 1, 1, 1, 2, 2, 4, 1.0),
        ts("Curacao", "CW", 3, 0, 1, 2, 1, 9, 1, 0.0),
      ],
      matches: [
        m("E_1_15186899", ["Germany","DE"], ["Curacao","CW"], 0.8632, 0, 0.1368, { played: true, s1: 7, s2: 1 }),
        m("E_1_15186904", ["Ivory Coast","CI"], ["Ecuador","EC"], 0.5851, 0, 0.4149, { played: true, s1: 1, s2: 0 }),
        m("E_2_15186905", ["Germany","DE"], ["Ivory Coast","CI"], 0.5459, 0, 0.4541, { played: true, s1: 2, s2: 1 }),
        m("E_2_15186906", ["Ecuador","EC"], ["Curacao","CW"], 0.7259, 0, 0.2741, { played: true, s1: 0, s2: 0 }),
        m("E_3_15186907", ["Ecuador","EC"], ["Germany","DE"], 0.3710, 0, 0.6290, { played: true, s1: 2, s2: 1 }),
        m("E_3_15186908", ["Curacao","CW"], ["Ivory Coast","CI"], 0.1759, 0, 0.8241, { played: true, s1: 0, s2: 2 }),
      ],
    },
    {
      id: "F", name: "Group F",
      teams: [
        ts("Netherlands", "NL", 3, 2, 1, 0, 10, 4, 7, 1.0),
        ts("Japan", "JP", 3, 1, 2, 0, 7, 3, 5, 1.0),
        ts("Sweden", "SE", 3, 1, 1, 1, 7, 7, 4, 1.0),
        ts("Tunisia", "TN", 3, 0, 0, 3, 2, 12, 0, 0.0),
      ],
      matches: [
        m("F_1_15186945", ["Netherlands","NL"], ["Japan","JP"], 0.6613, 0, 0.3387, { played: true, s1: 2, s2: 2 }),
        m("F_1_15186951", ["Sweden","SE"], ["Tunisia","TN"], 0.6935, 0, 0.3065, { played: true, s1: 5, s2: 1 }),
        m("F_2_15186957", ["Netherlands","NL"], ["Sweden","SE"], 0.7343, 0, 0.2657, { played: true, s1: 5, s2: 1 }),
        m("F_2_15186963", ["Tunisia","TN"], ["Japan","JP"], 0.2047, 0, 0.7953, { played: true, s1: 0, s2: 4 }),
        m("F_3_15186972", ["Japan","JP"], ["Sweden","SE"], 0.5860, 0, 0.4140, { played: true, s1: 1, s2: 1 }),
        m("F_3_15186973", ["Tunisia","TN"], ["Netherlands","NL"], 0.1379, 0, 0.8621, { played: true, s1: 1, s2: 3 }),
      ],
    },
    {
      id: "G", name: "Group G",
      teams: [
        ts("Belgium", "BE", 3, 1, 2, 0, 6, 2, 5, 1.0),
        ts("Egypt", "EG", 3, 1, 2, 0, 5, 3, 5, 1.0),
        ts("Iran", "IR", 3, 0, 3, 0, 3, 3, 3, 0.0),
        ts("New Zealand", "NZ", 3, 0, 1, 2, 4, 10, 1, 0.0),
      ],
      matches: [
        m("G_1_15186832", ["Iran","IR"], ["New Zealand","NZ"], 0.6836, 0, 0.3164, { played: true, s1: 2, s2: 2 }),
        m("G_1_15186837", ["Belgium","BE"], ["Egypt","EG"], 0.5441, 0, 0.4559, { played: true, s1: 1, s2: 1 }),
        m("G_2_15186499", ["Belgium","BE"], ["Iran","IR"], 0.6145, 0, 0.3855, { played: true, s1: 0, s2: 0 }),
        m("G_2_15186827", ["New Zealand","NZ"], ["Egypt","EG"], 0.2572, 0, 0.7428, { played: true, s1: 1, s2: 3 }),
        m("G_3_15186822", ["New Zealand","NZ"], ["Belgium","BE"], 0.1879, 0, 0.8121, { played: true, s1: 1, s2: 5 }),
        m("G_3_15186828", ["Egypt","EG"], ["Iran","IR"], 0.5072, 0, 0.4928, { played: true, s1: 1, s2: 1 }),
      ],
    },
    {
      id: "H", name: "Group H",
      teams: [
        ts("Spain", "ES", 3, 2, 1, 0, 5, 0, 7, 1.0),
        ts("Cape Verde", "CV", 3, 0, 3, 0, 2, 2, 3, 1.0),
        ts("Uruguay", "UY", 3, 0, 2, 1, 3, 4, 2, 0.0),
        ts("Saudi Arabia", "SA", 3, 0, 2, 1, 1, 5, 2, 0.0),
      ],
      matches: [
        m("H_1_15186783", ["Spain","ES"], ["Cape Verde","CV"], 0.7190, 0, 0.2810, { played: true, s1: 0, s2: 0 }),
        m("H_1_15186811", ["Saudi Arabia","SA"], ["Uruguay","UY"], 0.3353, 0, 0.6647, { played: true, s1: 1, s2: 1 }),
        m("H_2_15186800", ["Uruguay","UY"], ["Cape Verde","CV"], 0.6246, 0, 0.3754, { played: true, s1: 2, s2: 2 }),
        m("H_2_15186840", ["Spain","ES"], ["Saudi Arabia","SA"], 0.7530, 0, 0.2470, { played: true, s1: 4, s2: 0 }),
        m("H_3_15186803", ["Cape Verde","CV"], ["Saudi Arabia","SA"], 0.5437, 0, 0.4563, { played: true, s1: 0, s2: 0 }),
        m("H_3_15186841", ["Uruguay","UY"], ["Spain","ES"], 0.3941, 0, 0.6059, { played: true, s1: 0, s2: 1 }),
      ],
    },
    {
      id: "I", name: "Group I",
      teams: [
        ts("France", "FR", 3, 3, 0, 0, 10, 2, 9, 1.0),
        ts("Norway", "NO", 3, 2, 0, 1, 8, 7, 6, 1.0),
        ts("Senegal", "SN", 3, 1, 0, 2, 8, 6, 3, 1.0),
        ts("Iraq", "IQ", 3, 0, 0, 3, 1, 12, 0, 0.0),
      ],
      matches: [
        m("I_1_15186501", ["France","FR"], ["Senegal","SN"], 0.7681, 0, 0.2319, { played: true, s1: 3, s2: 1 }),
        m("I_1_15186773", ["Iraq","IQ"], ["Norway","NO"], 0.1489, 0, 0.8511, { played: true, s1: 1, s2: 4 }),
        m("I_2_15186769", ["France","FR"], ["Iraq","IQ"], 0.9425, 0, 0.0575, { played: true, s1: 3, s2: 0 }),
        m("I_2_15186770", ["Norway","NO"], ["Senegal","SN"], 0.4792, 0, 0.5208, { played: true, s1: 3, s2: 2 }),
        m("I_3_15186537", ["Norway","NO"], ["France","FR"], 0.2174, 0, 0.7826, { played: true, s1: 1, s2: 4 }),
        m("I_3_15186771", ["Senegal","SN"], ["Iraq","IQ"], 0.8613, 0, 0.1387, { played: true, s1: 5, s2: 0 }),
      ],
    },
    {
      id: "J", name: "Group J",
      teams: [
        ts("Argentina", "AR", 3, 3, 0, 0, 8, 1, 9, 1.0),
        ts("Austria", "AT", 3, 1, 1, 1, 6, 6, 4, 1.0),
        ts("Algeria", "DZ", 3, 1, 1, 1, 5, 7, 4, 1.0),
        ts("Jordan", "JO", 3, 0, 0, 3, 3, 8, 0, 0.0),
      ],
      matches: [
        m("J_1_15186751", ["Austria","AT"], ["Jordan","JO"], 0.5871, 0, 0.4129, { played: true, s1: 3, s2: 1 }),
        m("J_1_15186854", ["Argentina","AR"], ["Algeria","DZ"], 0.7834, 0, 0.2166, { played: true, s1: 3, s2: 0 }),
        m("J_2_15186502", ["Argentina","AR"], ["Austria","AT"], 0.8618, 0, 0.1382, { played: true, s1: 2, s2: 0 }),
        m("J_2_15186740", ["Jordan","JO"], ["Algeria","DZ"], 0.2898, 0, 0.7102, { played: true, s1: 1, s2: 2 }),
        m("J_3_15186734", ["Jordan","JO"], ["Argentina","AR"], 0.1013, 0, 0.8987, { played: true, s1: 1, s2: 3 }),
        m("J_3_15186747", ["Algeria","DZ"], ["Austria","AT"], 0.6329, 0, 0.3671, { played: true, s1: 3, s2: 3 }),
      ],
    },
    {
      id: "K", name: "Group K",
      teams: [
        ts("Colombia", "CO", 3, 2, 1, 0, 4, 1, 7, 1.0),
        ts("Portugal", "PT", 3, 1, 2, 0, 6, 1, 5, 1.0),
        ts("DR Congo", "CD", 3, 1, 1, 1, 4, 3, 4, 1.0),
        ts("Uzbekistan", "UZ", 3, 0, 0, 3, 2, 11, 0, 0.0),
      ],
      matches: [
        m("K_1_15186709", ["Portugal","PT"], ["DR Congo","CD"], 0.7557, 0, 0.2443, { played: true, s1: 1, s2: 1 }),
        m("K_1_15186722", ["Uzbekistan","UZ"], ["Colombia","CO"], 0.1502, 0, 0.8498, { played: true, s1: 1, s2: 3 }),
        m("K_2_15186713", ["Colombia","CO"], ["DR Congo","CD"], 0.7085, 0, 0.2915, { played: true, s1: 1, s2: 0 }),
        m("K_2_15186858", ["Portugal","PT"], ["Uzbekistan","UZ"], 0.8517, 0, 0.1483, { played: true, s1: 5, s2: 0 }),
        m("K_3_15186696", ["Colombia","CO"], ["Portugal","PT"], 0.5247, 0, 0.4753, { played: true, s1: 0, s2: 0 }),
        m("K_3_15186717", ["DR Congo","CD"], ["Uzbekistan","UZ"], 0.7449, 0, 0.2551, { played: true, s1: 3, s2: 1 }),
      ],
    },
    {
      id: "L", name: "Group L",
      teams: [
        ts("England", "GB", 3, 2, 1, 0, 6, 2, 7, 1.0),
        ts("Croatia", "HR", 3, 2, 0, 1, 5, 5, 6, 1.0),
        ts("Ghana", "GH", 3, 1, 1, 1, 2, 2, 4, 1.0),
        ts("Panama", "PA", 3, 0, 0, 3, 0, 4, 0, 0.0),
      ],
      matches: [
        m("L_1_15186504", ["England","GB"], ["Croatia","HR"], 0.5718, 0, 0.4282, { played: true, s1: 4, s2: 2 }),
        m("L_1_15186687", ["Ghana","GH"], ["Panama","PA"], 0.6353, 0, 0.3647, { played: true, s1: 1, s2: 0 }),
        m("L_2_15186520", ["Panama","PA"], ["Croatia","HR"], 0.3008, 0, 0.6992, { played: true, s1: 0, s2: 1 }),
        m("L_2_15186672", ["England","GB"], ["Ghana","GH"], 0.6140, 0, 0.3860, { played: true, s1: 0, s2: 0 }),
        m("L_3_15186624", ["Croatia","HR"], ["Ghana","GH"], 0.6774, 0, 0.3226, { played: true, s1: 2, s2: 1 }),
        m("L_3_15186676", ["Panama","PA"], ["England","GB"], 0.2437, 0, 0.7563, { played: true, s1: 0, s2: 2 }),
      ],
    },
  ],
  knockoutRounds: [
    {
      name: "Round of 32", shortName: "R32",
      matches: [
        m("R32_1", ["Germany","DE"], ["Paraguay","PY"], 0.7275, 0, 0.2725, { played: true, s1: 0, s2: 1 }),
        m("R32_2", ["France","FR"], ["Sweden","SE"], 0.8026, 0, 0.1974, { played: true, s1: 3, s2: 0 }),
        m("R32_3", ["South Africa","ZA"], ["Canada","CA"], 0.4180, 0, 0.5820, { played: true, s1: 0, s2: 1 }),
        m("R32_4", ["Netherlands","NL"], ["Morocco","MA"], 0.6402, 0, 0.3598, { played: true, s1: 0, s2: 1 }),
        m("R32_5", ["Portugal","PT"], ["Croatia","HR"], 0.4804, 0, 0.5196, { played: true, s1: 2, s2: 1 }),
        m("R32_6", ["Spain","ES"], ["Austria","AT"], 0.7707, 0, 0.2293, { played: true, s1: 3, s2: 0 }),
        m("R32_7", ["USA","US"], ["Bosnia and Herzegovina","BA"], 0.6921, 0, 0.3079, { played: true, s1: 2, s2: 0 }),
        m("R32_8", ["Belgium","BE"], ["Senegal","SN"], 0.6438, 0, 0.3562, { played: true, s1: 3, s2: 2 }),
        m("R32_9", ["Brazil","BR"], ["Japan","JP"], 0.4993, 0, 0.5007, { played: true, s1: 2, s2: 1 }),
        m("R32_10", ["Ivory Coast","CI"], ["Norway","NO"], 0.5672, 0, 0.4328, { played: true, s1: 1, s2: 2 }),
        m("R32_11", ["Mexico","MX"], ["Ecuador","EC"], 0.6557, 0, 0.3443, { played: true, s1: 2, s2: 0 }),
        m("R32_12", ["England","GB"], ["DR Congo","CD"], 0.7229, 0, 0.2771, { played: true, s1: 2, s2: 1 }),
        m("R32_13", ["Argentina","AR"], ["Cape Verde","CV"], 0.8260, 0, 0.1740, { played: true, s1: 3, s2: 2 }),
        m("R32_14", ["Australia","AU"], ["Egypt","EG"], 0.5521, 0, 0.4479, { played: true, s1: 0, s2: 1 }),
        m("R32_15", ["Switzerland","CH"], ["Algeria","DZ"], 0.6983, 0, 0.3017, { played: true, s1: 2, s2: 0 }),
        m("R32_16", ["Colombia","CO"], ["Ghana","GH"], 0.5971, 0, 0.4029, { played: true, s1: 1, s2: 0 }),
      ],
    },
    {
      name: "Round of 16", shortName: "R16",
      matches: [
        m("R16_1", ["Paraguay","PY"], ["France","FR"], 0.1872, 0, 0.8128, { played: true, s1: 0, s2: 1 }),
        m("R16_2", ["Canada","CA"], ["Morocco","MA"], 0.3205, 0, 0.6795, { played: true, s1: 0, s2: 3 }),
        m("R16_3", ["Portugal","PT"], ["Spain","ES"], 0.5020, 0, 0.4980, { played: true, s1: 0, s2: 1 }),
        m("R16_4", ["USA","US"], ["Belgium","BE"], 0.3215, 0, 0.6785, { played: true, s1: 1, s2: 4 }),
        m("R16_5", ["Brazil","BR"], ["Norway","NO"], 0.7164, 0, 0.2836, { played: true, s1: 1, s2: 2 }),
        m("R16_6", ["Mexico","MX"], ["England","GB"], 0.4995, 0, 0.5005, { played: true, s1: 2, s2: 3 }),
        m("R16_7", ["Argentina","AR"], ["Egypt","EG"], 0.7311, 0, 0.2689, { played: true, s1: 3, s2: 2 }),
        m("R16_8", ["Switzerland","CH"], ["Colombia","CO"], 0.5717, 0, 0.4283, { played: true, s1: 1, s2: 0 }),
      ],
    },
    {
      name: "Quarter-finals", shortName: "QF",
      matches: [
        m("QF_1", ["France","FR"], ["Morocco","MA"], 0.7304, 0, 0.2696, { played: true, s1: 2, s2: 0 }),
        m("QF_2", ["Spain","ES"], ["Belgium","BE"], 0.4579, 0, 0.5421, { played: true, s1: 2, s2: 1 }),
        m("QF_3", ["Norway","NO"], ["England","GB"], 0.3605, 0, 0.6395, { played: true, s1: 1, s2: 2 }),
        m("QF_4", ["Argentina","AR"], ["Switzerland","CH"], 0.6098, 0, 0.3902, {}),
      ],
    },
    {
      name: "Semi-finals", shortName: "SF",
      matches: [
        m("SF_1", ["France","FR"], ["Spain","ES"], 0.6256, 0, 0.3744, {}),
        m("SF_2", ["England","GB"], ["Argentina","AR"], 0.4197, 0, 0.5803, {}),
      ],
    },
    {
      name: "Final", shortName: "Final",
      matches: [
        m("Final_1", ["France","FR"], ["Argentina","AR"], 0.4739, 0, 0.5261, {}),
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 2022 — 32 teams, 8 groups, all played
// ══════════════════════════════════════════════════════════════════════════

export const tournament2022: TournamentData = {
  year: 2022,
  teamCount: 32,
  groups: [
    {
      id: "A", name: "Group A",
      teams: [
        ts("Netherlands","NL",3,2,1,0,5,1,7,0.92),
        ts("Senegal","SN",3,2,0,1,5,4,6,0.72),
        ts("Ecuador","EC",3,1,1,1,4,3,4,0.45),
        ts("Qatar","QA",3,0,0,3,1,7,0,0.04),
      ],
      matches: [
        m("22A1",["Qatar","QA"],      ["Ecuador","EC"],     0.28,0.26,0.46, { played:true, s1:0, s2:2, date:"Nov 20" }),
        m("22A2",["Senegal","SN"],    ["Netherlands","NL"], 0.27,0.26,0.47, { played:true, s1:0, s2:2, date:"Nov 21" }),
        m("22A3",["Qatar","QA"],      ["Senegal","SN"],     0.24,0.26,0.50, { played:true, s1:1, s2:3, date:"Nov 25" }),
        m("22A4",["Netherlands","NL"],["Ecuador","EC"],     0.52,0.27,0.21, { played:true, s1:1, s2:1, date:"Nov 25" }),
        m("22A5",["Ecuador","EC"],    ["Senegal","SN"],     0.43,0.28,0.29, { played:true, s1:1, s2:2, date:"Nov 29" }),
        m("22A6",["Qatar","QA"],      ["Netherlands","NL"], 0.18,0.21,0.61, { played:true, s1:0, s2:2, date:"Nov 29" }),
      ],
    },
    {
      id: "B", name: "Group B",
      teams: [
        ts("England","GB",3,2,1,0,9,2,7,0.94),
        ts("USA","US",3,1,2,0,2,1,5,0.76),
        ts("Iran","IR",3,1,0,2,4,7,3,0.34),
        ts("Wales","GB-WLS",3,0,1,2,1,6,1,0.08),
      ],
      matches: [
        m("22B1",["England","GB"],    ["Iran","IR"],        0.71,0.18,0.11, { played:true, s1:6, s2:2, date:"Nov 21" }),
        m("22B2",["USA","US"],        ["Wales","GB-WLS"],   0.47,0.28,0.25, { played:true, s1:1, s2:1, date:"Nov 21" }),
        m("22B3",["Wales","GB-WLS"],  ["Iran","IR"],        0.38,0.28,0.34, { played:true, s1:0, s2:2, date:"Nov 25" }),
        m("22B4",["England","GB"],    ["USA","US"],         0.52,0.27,0.21, { played:true, s1:0, s2:0, date:"Nov 25" }),
        m("22B5",["Wales","GB-WLS"],  ["England","GB"],     0.20,0.25,0.55, { played:true, s1:0, s2:3, date:"Nov 29" }),
        m("22B6",["Iran","IR"],       ["USA","US"],         0.30,0.27,0.43, { played:true, s1:0, s2:1, date:"Nov 29" }),
      ],
    },
    {
      id: "C", name: "Group C",
      teams: [
        ts("Argentina","AR",3,2,0,1,5,2,6,0.88),
        ts("Poland","PL",3,1,1,1,2,2,4,0.58),
        ts("Mexico","MX",3,1,1,1,2,3,4,0.52),
        ts("Saudi Arabia","SA",3,1,0,2,3,5,3,0.14),
      ],
      matches: [
        m("22C1",["Argentina","AR"],  ["Saudi Arabia","SA"],0.80,0.13,0.07, { played:true, s1:1, s2:2, date:"Nov 22" }),
        m("22C2",["Mexico","MX"],     ["Poland","PL"],      0.38,0.29,0.33, { played:true, s1:0, s2:0, date:"Nov 22" }),
        m("22C3",["Poland","PL"],     ["Saudi Arabia","SA"],0.50,0.27,0.23, { played:true, s1:2, s2:0, date:"Nov 26" }),
        m("22C4",["Argentina","AR"],  ["Mexico","MX"],      0.58,0.24,0.18, { played:true, s1:2, s2:0, date:"Nov 26" }),
        m("22C5",["Poland","PL"],     ["Argentina","AR"],   0.22,0.24,0.54, { played:true, s1:0, s2:2, date:"Nov 30" }),
        m("22C6",["Saudi Arabia","SA"],["Mexico","MX"],     0.30,0.27,0.43, { played:true, s1:1, s2:2, date:"Nov 30" }),
      ],
    },
    {
      id: "D", name: "Group D",
      teams: [
        ts("France","FR",3,2,0,1,6,3,6,0.86),
        ts("Australia","AU",3,2,0,1,5,5,6,0.70),
        ts("Tunisia","TN",3,1,1,1,1,1,4,0.42),
        ts("Denmark","DK",3,0,1,2,1,4,1,0.14),
      ],
      matches: [
        m("22D1",["Denmark","DK"],    ["Tunisia","TN"],     0.42,0.30,0.28, { played:true, s1:0, s2:0, date:"Nov 22" }),
        m("22D2",["France","FR"],     ["Australia","AU"],   0.67,0.20,0.13, { played:true, s1:4, s2:1, date:"Nov 22" }),
        m("22D3",["Tunisia","TN"],    ["Australia","AU"],   0.35,0.30,0.35, { played:true, s1:0, s2:1, date:"Nov 26" }),
        m("22D4",["France","FR"],     ["Denmark","DK"],     0.58,0.24,0.18, { played:true, s1:2, s2:1, date:"Nov 26" }),
        m("22D5",["Tunisia","TN"],    ["France","FR"],      0.18,0.22,0.60, { played:true, s1:1, s2:0, date:"Nov 30" }),
        m("22D6",["Australia","AU"],  ["Denmark","DK"],     0.44,0.28,0.28, { played:true, s1:1, s2:0, date:"Nov 30" }),
      ],
    },
    {
      id: "E", name: "Group E",
      teams: [
        ts("Japan","JP",3,2,0,1,4,3,6,0.74),
        ts("Spain","ES",3,1,1,1,9,3,4,0.70),
        ts("Germany","DE",3,1,1,1,6,5,4,0.42),
        ts("Costa Rica","CR",3,1,0,2,3,11,3,0.22),
      ],
      matches: [
        m("22E1",["Germany","DE"],    ["Japan","JP"],       0.60,0.22,0.18, { played:true, s1:1, s2:2, date:"Nov 23" }),
        m("22E2",["Spain","ES"],      ["Costa Rica","CR"],  0.78,0.14,0.08, { played:true, s1:7, s2:0, date:"Nov 23" }),
        m("22E3",["Japan","JP"],      ["Costa Rica","CR"],  0.55,0.25,0.20, { played:true, s1:0, s2:1, date:"Nov 27" }),
        m("22E4",["Spain","ES"],      ["Germany","DE"],     0.47,0.26,0.27, { played:true, s1:1, s2:1, date:"Nov 27" }),
        m("22E5",["Japan","JP"],      ["Spain","ES"],       0.28,0.26,0.46, { played:true, s1:2, s2:1, date:"Dec 1" }),
        m("22E6",["Costa Rica","CR"], ["Germany","DE"],     0.22,0.23,0.55, { played:true, s1:2, s2:4, date:"Dec 1" }),
      ],
    },
    {
      id: "F", name: "Group F",
      teams: [
        ts("Morocco","MA",3,2,1,0,4,1,7,0.91),
        ts("Croatia","HR",3,1,2,0,4,1,5,0.76),
        ts("Belgium","BE",3,1,1,1,1,2,4,0.40),
        ts("Canada","CA",3,0,0,3,2,7,0,0.04),
      ],
      matches: [
        m("22F1",["Morocco","MA"],    ["Croatia","HR"],     0.38,0.30,0.32, { played:true, s1:0, s2:0, date:"Nov 23" }),
        m("22F2",["Belgium","BE"],    ["Canada","CA"],      0.67,0.19,0.14, { played:true, s1:1, s2:0, date:"Nov 23" }),
        m("22F3",["Belgium","BE"],    ["Morocco","MA"],     0.44,0.28,0.28, { played:true, s1:0, s2:2, date:"Nov 27" }),
        m("22F4",["Croatia","HR"],    ["Canada","CA"],      0.60,0.23,0.17, { played:true, s1:4, s2:1, date:"Nov 27" }),
        m("22F5",["Croatia","HR"],    ["Belgium","BE"],     0.38,0.29,0.33, { played:true, s1:0, s2:0, date:"Dec 1" }),
        m("22F6",["Canada","CA"],     ["Morocco","MA"],     0.18,0.22,0.60, { played:true, s1:1, s2:2, date:"Dec 1" }),
      ],
    },
    {
      id: "G", name: "Group G",
      teams: [
        ts("Brazil","BR",3,2,0,1,3,1,6,0.88),
        ts("Switzerland","CH",3,2,0,1,4,3,6,0.72),
        ts("Cameroon","CM",3,1,1,1,4,4,4,0.38),
        ts("Serbia","RS",3,0,1,2,5,8,1,0.10),
      ],
      matches: [
        m("22G1",["Brazil","BR"],     ["Serbia","RS"],      0.72,0.18,0.10, { played:true, s1:2, s2:0, date:"Nov 24" }),
        m("22G2",["Switzerland","CH"],["Cameroon","CM"],    0.50,0.27,0.23, { played:true, s1:1, s2:0, date:"Nov 24" }),
        m("22G3",["Cameroon","CM"],   ["Serbia","RS"],      0.42,0.29,0.29, { played:true, s1:3, s2:3, date:"Nov 28" }),
        m("22G4",["Brazil","BR"],     ["Switzerland","CH"], 0.57,0.24,0.19, { played:true, s1:1, s2:0, date:"Nov 28" }),
        m("22G5",["Cameroon","CM"],   ["Brazil","BR"],      0.14,0.20,0.66, { played:true, s1:1, s2:0, date:"Dec 2" }),
        m("22G6",["Serbia","RS"],     ["Switzerland","CH"], 0.30,0.26,0.44, { played:true, s1:2, s2:3, date:"Dec 2" }),
      ],
    },
    {
      id: "H", name: "Group H",
      teams: [
        ts("Portugal","PT",3,2,0,1,6,4,6,0.82),
        ts("South Korea","KR",3,1,1,1,4,4,4,0.60),
        ts("Uruguay","UY",3,1,1,1,2,2,4,0.52),
        ts("Ghana","GH",3,1,0,2,5,7,3,0.18),
      ],
      matches: [
        m("22H1",["Uruguay","UY"],    ["South Korea","KR"], 0.40,0.28,0.32, { played:true, s1:0, s2:0, date:"Nov 24" }),
        m("22H2",["Portugal","PT"],   ["Ghana","GH"],       0.68,0.19,0.13, { played:true, s1:3, s2:2, date:"Nov 24" }),
        m("22H3",["South Korea","KR"],["Ghana","GH"],       0.48,0.28,0.24, { played:true, s1:2, s2:3, date:"Nov 28" }),
        m("22H4",["Portugal","PT"],   ["Uruguay","UY"],     0.52,0.26,0.22, { played:true, s1:2, s2:0, date:"Nov 28" }),
        m("22H5",["South Korea","KR"],["Portugal","PT"],    0.26,0.25,0.49, { played:true, s1:2, s2:1, date:"Dec 2" }),
        m("22H6",["Ghana","GH"],      ["Uruguay","UY"],     0.34,0.27,0.39, { played:true, s1:0, s2:2, date:"Dec 2" }),
      ],
    },
  ],
  knockoutRounds: [
    {
      name: "Round of 16", shortName: "R16",
      matches: [
        m("22R16_1",["Netherlands","NL"],["USA","US"],       0.56,0.24,0.20, { played:true, s1:3, s2:1, date:"Dec 3" }),
        m("22R16_2",["Argentina","AR"],  ["Australia","AU"], 0.72,0.18,0.10, { played:true, s1:2, s2:1, date:"Dec 3" }),
        m("22R16_3",["France","FR"],     ["Poland","PL"],    0.64,0.21,0.15, { played:true, s1:3, s2:1, date:"Dec 4" }),
        m("22R16_4",["England","GB"],    ["Senegal","SN"],   0.60,0.23,0.17, { played:true, s1:3, s2:0, date:"Dec 4" }),
        m("22R16_5",["Japan","JP"],      ["Croatia","HR"],   0.42,0.27,0.31, { played:true, s1:1, s2:1, date:"Dec 5" }),
        m("22R16_6",["Brazil","BR"],     ["South Korea","KR"],0.72,0.18,0.10,{ played:true, s1:4, s2:1, date:"Dec 5" }),
        m("22R16_7",["Morocco","MA"],    ["Spain","ES"],     0.34,0.26,0.40, { played:true, s1:0, s2:0, date:"Dec 6" }),
        m("22R16_8",["Portugal","PT"],   ["Switzerland","CH"],0.60,0.22,0.18,{ played:true, s1:6, s2:1, date:"Dec 6" }),
      ],
    },
    {
      name: "Quarter-finals", shortName: "QF",
      matches: [
        m("22QF_1",["Netherlands","NL"],["Argentina","AR"], 0.34,0.26,0.40, { played:true, s1:2, s2:2, date:"Dec 9" }),
        m("22QF_2",["France","FR"],     ["England","GB"],   0.48,0.26,0.26, { played:true, s1:2, s2:1, date:"Dec 10" }),
        m("22QF_3",["Croatia","HR"],    ["Brazil","BR"],    0.30,0.24,0.46, { played:true, s1:1, s2:1, date:"Dec 9" }),
        m("22QF_4",["Morocco","MA"],    ["Portugal","PT"],  0.33,0.26,0.41, { played:true, s1:1, s2:0, date:"Dec 10" }),
      ],
    },
    {
      name: "Semi-finals", shortName: "SF",
      matches: [
        m("22SF_1",["Argentina","AR"],["Croatia","HR"],  0.58,0.23,0.19, { played:true, s1:3, s2:0, date:"Dec 13" }),
        m("22SF_2",["France","FR"],   ["Morocco","MA"],  0.62,0.22,0.16, { played:true, s1:2, s2:0, date:"Dec 14" }),
      ],
    },
    {
      name: "Final", shortName: "Final",
      matches: [
        m("22FIN_1",["Argentina","AR"],["France","FR"], 0.44,0.24,0.32, { played:true, s1:3, s2:3, date:"Dec 18" }),
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 2018 — 32 teams, 8 groups, all played
// ══════════════════════════════════════════════════════════════════════════

export const tournament2018: TournamentData = {
  year: 2018,
  teamCount: 32,
  groups: [
    {
      id: "A", name: "Group A",
      teams: [
        ts("Uruguay","UY",3,3,0,0,5,0,9,0.97),
        ts("Russia","RU",3,2,0,1,8,4,6,0.78),
        ts("Saudi Arabia","SA",3,1,0,2,2,7,3,0.20),
        ts("Egypt","EG",3,0,0,3,2,6,0,0.05),
      ],
      matches: [
        m("18A1",["Russia","RU"],     ["Saudi Arabia","SA"],0.60,0.22,0.18, { played:true, s1:5, s2:0, date:"Jun 14" }),
        m("18A2",["Egypt","EG"],      ["Uruguay","UY"],     0.18,0.22,0.60, { played:true, s1:0, s2:1, date:"Jun 15" }),
        m("18A3",["Russia","RU"],     ["Egypt","EG"],       0.55,0.25,0.20, { played:true, s1:3, s2:0, date:"Jun 19" }),
        m("18A4",["Uruguay","UY"],    ["Saudi Arabia","SA"],0.67,0.20,0.13, { played:true, s1:1, s2:0, date:"Jun 20" }),
        m("18A5",["Uruguay","UY"],    ["Russia","RU"],      0.50,0.26,0.24, { played:true, s1:3, s2:0, date:"Jun 25" }),
        m("18A6",["Saudi Arabia","SA"],["Egypt","EG"],      0.44,0.29,0.27, { played:true, s1:2, s2:1, date:"Jun 25" }),
      ],
    },
    {
      id: "B", name: "Group B",
      teams: [
        ts("Spain","ES",3,1,2,0,6,5,5,0.74),
        ts("Portugal","PT",3,1,2,0,6,5,5,0.72),
        ts("Iran","IR",3,1,1,1,2,2,4,0.36),
        ts("Morocco","MA",3,0,1,2,2,4,1,0.16),
      ],
      matches: [
        m("18B1",["Portugal","PT"],   ["Spain","ES"],       0.38,0.28,0.34, { played:true, s1:3, s2:3, date:"Jun 15" }),
        m("18B2",["Morocco","MA"],    ["Iran","IR"],        0.40,0.29,0.31, { played:true, s1:0, s2:1, date:"Jun 15" }),
        m("18B3",["Portugal","PT"],   ["Morocco","MA"],     0.62,0.22,0.16, { played:true, s1:1, s2:0, date:"Jun 20" }),
        m("18B4",["Iran","IR"],       ["Spain","ES"],       0.18,0.22,0.60, { played:true, s1:0, s2:1, date:"Jun 20" }),
        m("18B5",["Iran","IR"],       ["Portugal","PT"],    0.24,0.25,0.51, { played:true, s1:1, s2:1, date:"Jun 25" }),
        m("18B6",["Spain","ES"],      ["Morocco","MA"],     0.56,0.25,0.19, { played:true, s1:2, s2:2, date:"Jun 25" }),
      ],
    },
    {
      id: "C", name: "Group C",
      teams: [
        ts("France","FR",3,2,1,0,3,1,7,0.91),
        ts("Denmark","DK",3,1,2,0,2,1,5,0.68),
        ts("Peru","PE",3,1,0,2,2,2,3,0.28),
        ts("Australia","AU",3,0,1,2,2,5,1,0.14),
      ],
      matches: [
        m("18C1",["France","FR"],     ["Australia","AU"],   0.67,0.20,0.13, { played:true, s1:2, s2:1, date:"Jun 16" }),
        m("18C2",["Peru","PE"],       ["Denmark","DK"],     0.36,0.28,0.36, { played:true, s1:0, s2:1, date:"Jun 16" }),
        m("18C3",["Denmark","DK"],    ["Australia","AU"],   0.50,0.28,0.22, { played:true, s1:1, s2:1, date:"Jun 21" }),
        m("18C4",["France","FR"],     ["Peru","PE"],        0.63,0.22,0.15, { played:true, s1:1, s2:0, date:"Jun 21" }),
        m("18C5",["Denmark","DK"],    ["France","FR"],      0.24,0.28,0.48, { played:true, s1:0, s2:0, date:"Jun 26" }),
        m("18C6",["Australia","AU"],  ["Peru","PE"],        0.36,0.28,0.36, { played:true, s1:0, s2:2, date:"Jun 26" }),
      ],
    },
    {
      id: "D", name: "Group D",
      teams: [
        ts("Croatia","HR",3,3,0,0,7,1,9,0.96),
        ts("Argentina","AR",3,1,1,1,3,5,4,0.68),
        ts("Nigeria","NG",3,1,0,2,3,4,3,0.26),
        ts("Iceland","IS",3,0,1,2,2,5,1,0.11),
      ],
      matches: [
        m("18D1",["Argentina","AR"],  ["Iceland","IS"],     0.62,0.22,0.16, { played:true, s1:1, s2:1, date:"Jun 16" }),
        m("18D2",["Croatia","HR"],    ["Nigeria","NG"],     0.56,0.24,0.20, { played:true, s1:2, s2:0, date:"Jun 16" }),
        m("18D3",["Argentina","AR"],  ["Croatia","HR"],     0.38,0.26,0.36, { played:true, s1:0, s2:3, date:"Jun 21" }),
        m("18D4",["Nigeria","NG"],    ["Iceland","IS"],     0.48,0.28,0.24, { played:true, s1:2, s2:0, date:"Jun 22" }),
        m("18D5",["Iceland","IS"],    ["Croatia","HR"],     0.18,0.22,0.60, { played:true, s1:1, s2:2, date:"Jun 26" }),
        m("18D6",["Nigeria","NG"],    ["Argentina","AR"],   0.26,0.24,0.50, { played:true, s1:1, s2:2, date:"Jun 26" }),
      ],
    },
    {
      id: "E", name: "Group E",
      teams: [
        ts("Brazil","BR",3,2,1,0,8,3,7,0.93),
        ts("Switzerland","CH",3,1,2,0,5,4,5,0.70),
        ts("Serbia","RS",3,1,0,2,2,4,3,0.28),
        ts("Costa Rica","CR",3,0,1,2,2,6,1,0.10),
      ],
      matches: [
        m("18E1",["Brazil","BR"],     ["Switzerland","CH"], 0.52,0.26,0.22, { played:true, s1:1, s2:1, date:"Jun 17" }),
        m("18E2",["Costa Rica","CR"], ["Serbia","RS"],      0.30,0.28,0.42, { played:true, s1:0, s2:1, date:"Jun 17" }),
        m("18E3",["Brazil","BR"],     ["Costa Rica","CR"],  0.74,0.17,0.09, { played:true, s1:2, s2:0, date:"Jun 22" }),
        m("18E4",["Serbia","RS"],     ["Switzerland","CH"], 0.36,0.28,0.36, { played:true, s1:1, s2:2, date:"Jun 22" }),
        m("18E5",["Brazil","BR"],     ["Serbia","RS"],      0.66,0.21,0.13, { played:true, s1:2, s2:0, date:"Jun 27" }),
        m("18E6",["Switzerland","CH"],["Costa Rica","CR"],  0.54,0.26,0.20, { played:true, s1:2, s2:2, date:"Jun 27" }),
      ],
    },
    {
      id: "F", name: "Group F",
      teams: [
        ts("Sweden","SE",3,2,0,1,6,2,6,0.78),
        ts("Mexico","MX",3,2,0,1,3,4,6,0.60),
        ts("South Korea","KR",3,1,0,2,3,4,3,0.28),
        ts("Germany","DE",3,1,0,2,2,4,3,0.24),
      ],
      matches: [
        m("18F1",["Germany","DE"],    ["Mexico","MX"],      0.56,0.24,0.20, { played:true, s1:0, s2:1, date:"Jun 17" }),
        m("18F2",["Sweden","SE"],     ["South Korea","KR"], 0.52,0.27,0.21, { played:true, s1:1, s2:0, date:"Jun 18" }),
        m("18F3",["Germany","DE"],    ["Sweden","SE"],      0.52,0.26,0.22, { played:true, s1:2, s2:1, date:"Jun 23" }),
        m("18F4",["South Korea","KR"],["Mexico","MX"],      0.30,0.28,0.42, { played:true, s1:1, s2:2, date:"Jun 23" }),
        m("18F5",["Germany","DE"],    ["South Korea","KR"], 0.68,0.19,0.13, { played:true, s1:0, s2:2, date:"Jun 27" }),
        m("18F6",["Mexico","MX"],     ["Sweden","SE"],      0.38,0.28,0.34, { played:true, s1:0, s2:3, date:"Jun 27" }),
      ],
    },
    {
      id: "G", name: "Group G",
      teams: [
        ts("Belgium","BE",3,3,0,0,9,2,9,0.95),
        ts("England","GB",3,2,1,0,8,3,7,0.90),
        ts("Tunisia","TN",3,1,0,2,2,8,3,0.20),
        ts("Panama","PA",3,0,0,3,2,11,0,0.04),
      ],
      matches: [
        m("18G1",["Belgium","BE"],    ["Panama","PA"],      0.80,0.13,0.07, { played:true, s1:3, s2:0, date:"Jun 18" }),
        m("18G2",["Tunisia","TN"],    ["England","GB"],     0.22,0.22,0.56, { played:true, s1:1, s2:2, date:"Jun 18" }),
        m("18G3",["Belgium","BE"],    ["Tunisia","TN"],     0.66,0.20,0.14, { played:true, s1:5, s2:2, date:"Jun 23" }),
        m("18G4",["England","GB"],    ["Panama","PA"],      0.80,0.13,0.07, { played:true, s1:6, s2:1, date:"Jun 24" }),
        m("18G5",["England","GB"],    ["Belgium","BE"],     0.38,0.27,0.35, { played:true, s1:0, s2:1, date:"Jun 28" }),
        m("18G6",["Panama","PA"],     ["Tunisia","TN"],     0.30,0.28,0.42, { played:true, s1:1, s2:2, date:"Jun 28" }),
      ],
    },
    {
      id: "H", name: "Group H",
      teams: [
        ts("Japan","JP",3,1,1,1,6,6,4,0.62),
        ts("Senegal","SN",3,1,1,1,4,4,4,0.60),
        ts("Colombia","CO",3,1,1,1,6,5,4,0.56),
        ts("Poland","PL",3,1,0,2,2,5,3,0.28),
      ],
      matches: [
        m("18H1",["Colombia","CO"],   ["Japan","JP"],       0.50,0.27,0.23, { played:true, s1:1, s2:2, date:"Jun 19" }),
        m("18H2",["Poland","PL"],     ["Senegal","SN"],     0.40,0.28,0.32, { played:true, s1:1, s2:2, date:"Jun 19" }),
        m("18H3",["Japan","JP"],      ["Senegal","SN"],     0.40,0.29,0.31, { played:true, s1:2, s2:2, date:"Jun 24" }),
        m("18H4",["Poland","PL"],     ["Colombia","CO"],    0.36,0.27,0.37, { played:true, s1:0, s2:3, date:"Jun 24" }),
        m("18H5",["Japan","JP"],      ["Poland","PL"],      0.44,0.28,0.28, { played:true, s1:0, s2:1, date:"Jun 28" }),
        m("18H6",["Senegal","SN"],    ["Colombia","CO"],    0.36,0.28,0.36, { played:true, s1:0, s2:1, date:"Jun 28" }),
      ],
    },
  ],
  knockoutRounds: [
    {
      name: "Round of 16", shortName: "R16",
      matches: [
        m("18R16_1",["France","FR"],    ["Argentina","AR"],  0.50,0.26,0.24, { played:true, s1:4, s2:3, date:"Jun 30" }),
        m("18R16_2",["Uruguay","UY"],   ["Portugal","PT"],   0.48,0.26,0.26, { played:true, s1:2, s2:1, date:"Jun 30" }),
        m("18R16_3",["Russia","RU"],    ["Spain","ES"],      0.28,0.24,0.48, { played:true, s1:1, s2:1, date:"Jul 1" }),
        m("18R16_4",["Croatia","HR"],   ["Denmark","DK"],    0.50,0.27,0.23, { played:true, s1:1, s2:1, date:"Jul 1" }),
        m("18R16_5",["Brazil","BR"],    ["Mexico","MX"],     0.66,0.20,0.14, { played:true, s1:2, s2:0, date:"Jul 2" }),
        m("18R16_6",["Belgium","BE"],   ["Japan","JP"],      0.62,0.22,0.16, { played:true, s1:3, s2:2, date:"Jul 2" }),
        m("18R16_7",["Sweden","SE"],    ["Switzerland","CH"],0.48,0.28,0.24, { played:true, s1:1, s2:0, date:"Jul 3" }),
        m("18R16_8",["Colombia","CO"],  ["England","GB"],    0.36,0.27,0.37, { played:true, s1:1, s2:1, date:"Jul 3" }),
      ],
    },
    {
      name: "Quarter-finals", shortName: "QF",
      matches: [
        m("18QF_1",["Uruguay","UY"],   ["France","FR"],     0.36,0.26,0.38, { played:true, s1:0, s2:2, date:"Jul 6" }),
        m("18QF_2",["Russia","RU"],    ["Croatia","HR"],    0.36,0.27,0.37, { played:true, s1:2, s2:2, date:"Jul 7" }),
        m("18QF_3",["Brazil","BR"],    ["Belgium","BE"],    0.52,0.25,0.23, { played:true, s1:1, s2:2, date:"Jul 6" }),
        m("18QF_4",["Sweden","SE"],    ["England","GB"],    0.40,0.28,0.32, { played:true, s1:0, s2:2, date:"Jul 7" }),
      ],
    },
    {
      name: "Semi-finals", shortName: "SF",
      matches: [
        m("18SF_1",["France","FR"],   ["Belgium","BE"],    0.52,0.25,0.23, { played:true, s1:1, s2:0, date:"Jul 10" }),
        m("18SF_2",["Croatia","HR"],  ["England","GB"],    0.46,0.27,0.27, { played:true, s1:2, s2:1, date:"Jul 11" }),
      ],
    },
    {
      name: "Final", shortName: "Final",
      matches: [
        m("18FIN_1",["France","FR"],  ["Croatia","HR"],    0.56,0.23,0.21, { played:true, s1:4, s2:2, date:"Jul 15" }),
      ],
    },
  ],
};

export const allTournaments: { [year: number]: TournamentData } = {
  2026: tournament2026,
  2022: tournament2022,
  2018: tournament2018,
};
