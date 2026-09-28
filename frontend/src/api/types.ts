// Mirrors the JSON shapes produced by medicina_naturista/web/main.py and
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
  matchLabel: string;
}

export interface FragmentsMessage {
  kind: "fragments";
  role: "assistant";
  searchId: string;
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

export interface GenerateResponse {
  messages: ChatMessage[];
  ownerNotice: string | null;
}
