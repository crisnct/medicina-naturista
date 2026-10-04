// Mirrors the JSON shapes produced by backend/web/main.py and
// web/handlers.py's message builders. Kept in sync by hand (no live
// deployment to generate this from OpenAPI yet) — see the backend module
// docstrings for the authoritative shape.

export interface TextMessage {
  kind: "text";
  role: "user" | "assistant";
  content: string;
}

export interface FragmentItem {
  document: string;
  text: string;
  relevancePercent: number | null;
  semanticScore: number | null;
  lexicalScore: number | null;
  // Where the condition the patient named was found: in the fragment's title, in its text, or nowhere.
  conditionMatch: "title" | "text" | null;
  matchLabel: string;
  foundByLexical: boolean;
}

// The signals a search's score is made of (chosen in the "Căutare avansată" panel).
export interface SearchSignals {
  conditions: boolean;
  lexical: boolean;
  semantic: boolean;
}

export interface FragmentsMessage {
  kind: "fragments";
  role: "assistant";
  searchId: string;
  // The signals this search was scored with; absent on messages from before the
  // choice existed, which were scored with every signal.
  signals?: SearchSignals;
  fragmentsCount: number;
  documentsCount: number;
  fragments: FragmentItem[];
}

export interface GenerateMessage {
  kind: "generate";
  role: "assistant";
  searchId: string;
  busy: boolean;
}

export interface DownloadMessage {
  kind: "download";
  role: "assistant";
  reportId: string;
  url: string;
  filename: string;
}

export type ChatMessage = TextMessage | FragmentsMessage | GenerateMessage | DownloadMessage;

export interface CategoryNode {
  id: string;
  label: string;
  ownDocuments: number;
  totalDocuments: number;
  isReal: boolean;
  children: CategoryNode[];
}

export interface SessionResponse {
  history: ChatMessage[];
}

export interface CategoriesResponse {
  tree: CategoryNode | null;
  defaultSelection: string[];
}

export interface MessagesResponse {
  messages: ChatMessage[];
}

export interface SendMessageResponse {
  messages: ChatMessage[];
  // True when POST /api/search should be called next to actually run
  // retrieval — kept as a separate, slower call so the echo/notice above
  // render immediately instead of waiting for the search to finish too.
  startSearch: boolean;
  // True when POST /api/condition should be called first: the dictionary does
  // not know the condition, so the AI is asked for it before the search starts.
  identifyCondition?: boolean;
}

export interface ConditionResponse {
  messages: ChatMessage[];
  startSearch: boolean;
}

export interface GenerateResponse {
  messages: ChatMessage[];
  ownerNotice: string | null;
}
