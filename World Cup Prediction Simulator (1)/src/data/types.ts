export interface Team {
  name: string;
  code: string;
}

export interface MatchResult {
  score1: number;
  score2: number;
}

export interface TeamStats {
  team: Team;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  points: number;
  advanceProb: number;
}

export interface MatchPrediction {
  id: string;
  team1: Team;
  team2: Team;
  prob1: number;
  probDraw: number;
  prob2: number;
  // actual match data
  played?: boolean;
  result?: MatchResult;
  date?: string;
}

export interface Group {
  id: string;
  name: string;
  teams: TeamStats[];
  matches: MatchPrediction[]; // 6 matches: indices 0-1=matchday1, 2-3=matchday2, 4-5=matchday3
}

export interface KnockoutRound {
  name: string;
  shortName: string;
  matches: MatchPrediction[];
}

export interface TournamentData {
  year: number;
  teamCount: number;
  groups: Group[];
  knockoutRounds: KnockoutRound[];
}

// Stage IDs in chronological order
export const GROUP_ROUND_IDS = ["GR1", "GR2", "GR3"] as const;
export type StageId = string;
