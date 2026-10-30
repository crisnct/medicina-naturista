// Mirrors the JSON shapes produced by backend/web/main.py and
// web/handlers.py's message builders. Kept in sync by hand (no live
// deployment to generate this from OpenAPI yet) — see the backend module
// docstrings for the authoritative shape.

export interface MessageIdentity {
  language?: "ro" | "en";
  groupId?: string;
}

export interface TextMessage extends MessageIdentity {
  kind: "text";
  role: "user" | "assistant";
  content: string;
  // Generation failures render only in their search's action panel.
  generationSearchId?: string;
}

export interface FragmentItem {
  document: string;
  text: string;
  // Original evidence text length, before display whitespace normalization.
  charactersCount?: number;
  relevancePercent: number | null;
  semanticScore: number | null;
  lexicalScore: number | null;
  // Where the condition the patient named was found: in the fragment's title, in its text, or nowhere.
  conditionMatch: "title" | "text" | null;
  matchLabel: string;
  foundByLexical: boolean;
}

// The signals a search's score is made of (chosen in the "Surse și opțiuni de căutare" panel).
export interface SearchSignals {
  conditions: boolean;
  lexical: boolean;
  semantic: boolean;
}

export interface FragmentsMessage extends MessageIdentity {
  kind: "fragments";
  role: "assistant";
  searchId: string;
  // The signals this search was scored with; absent on messages from before the
  // choice existed, which were scored with every signal.
  signals?: SearchSignals;
  indexGeneration?: string | null;
  removedCategoryIds?: string[];
  fragmentsCount: number;
  documentsCount: number;
  fragments: FragmentItem[];
}

export interface GenerateMessage extends MessageIdentity {
  kind: "generate";
  role: "assistant";
  searchId: string;
  busy: boolean;
}

export type ReportModel = "ollama-gemma4:12b" | "ollama-gemma3:1b" | "ollama-qwen3.5:9b" | "ollama-qwen3.5:4b"
  | "ollama-ministral-3:8b" | "ollama-deepseek-r1:8b" | "deepseek-flash"
  | "huggingface-deepseek-v4-flash" | "grok-4.3";

export interface ReportModelsResponse {
  models: ReportModel[];
  defaultModel?: ReportModel | null;
  allowedModels?: ReportModel[];
}

export interface ReportDurationEstimate {
  model: ReportModel;
  characters: number;
  estimatedSeconds: number | null;
  sampleCount: number;
}

export interface DownloadMessage extends MessageIdentity {
  kind: "download";
  role: "assistant";
  reportId: string;
  url: string;
  filename: string;
}

export type HerbEvidenceKind = "positive" | "contraindication";

export interface HerbConditionsMessage extends MessageIdentity {
  herbAgreement?: "masculine" | "feminine" | "plural";
  kind: "herb_conditions";
  role: "assistant";
  herbName: string;
  species: string[];
  entriesCount: number;
  conditions: { id: number; name: string }[];
  herbId?: number;
  positiveRunId?: string;
  fragmentsCount?: number;
  documentsCount?: number;
  cautionRunId?: string | null;
  contraindicationsStatus?: "ready" | "partial" | "not_ready" | "stale";
  contraindicationsCount?: number | null;
  contraindications?: { id: number; name: string; hasRecommendation: boolean }[];
  contraindicationFragmentsCount?: number;
  contraindicationDocumentsCount?: number;
  safetyRunId?: string | null;
  warningsStatus?: "ready" | "partial" | "not_ready" | "stale";
  warningsCount?: number | null;
  warningFragmentsCount?: number;
  warningDocumentsCount?: number;
  warningCandidateFragmentsCount?: number;
}

// Half-open Unicode code-point offsets, matching Python's unchanged source strings.
export interface HerbHighlight {
  start: number;
  end: number;
  kind: "herb" | "condition" | "warning";
}

export interface HerbWarning {
  id: string;
  text: string;
  kind: string;
  partners: string[];
  sourcesCount: number;
}

export interface HerbSafetyPage {
  herbId: number;
  safetyRunId: string;
  warningsStatus: "ready" | "partial" | "not_ready" | "stale";
  warningsCount: number;
  warnings: HerbWarning[];
  nextOffset: number | null;
}

export interface HerbSafetyEvidencePage {
  herbId: number;
  safetyRunId: string;
  warningId: string;
  fragmentsCount: number;
  documentsCount: number;
  fragments: HerbEvidenceFragment[];
  nextOffset: number | null;
}

export interface HerbEvidenceFragment {
  chunkId: number;
  document: string;
  lineStart: number;
  lineEnd: number;
  heading: string;
  text: string;
  conditions: { id: number; name: string }[];
  headingHighlights: HerbHighlight[];
  textHighlights: HerbHighlight[];
}

export interface HerbEvidencePage {
  herbId: number;
  positiveRunId: string;
  fragmentsCount: number;
  documentsCount: number;
  fragments: HerbEvidenceFragment[];
  nextOffset: number | null;
  evidenceKind?: HerbEvidenceKind;
  cautionRunId?: string;
}

export type ChatMessage = TextMessage | FragmentsMessage | GenerateMessage | DownloadMessage | HerbConditionsMessage;

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
  latestReportId?: string | null;
  generations?: ReportGeneration[];
}

export interface StartupStatus {
  status: "initializing" | "ready" | "degraded";
  message: string | null;
}

export interface AIActivity {
  phase: "waiting" | "processing" | "thinking" | "answering";
  lastActivityAgeMs: number | null;
  firstEventElapsedMs: number | null;
  firstThinkingElapsedMs: number | null;
  firstAnswerElapsedMs: number | null;
  thinkingCharactersReceived: number;
}

export interface ReportBatchPreview {
  index: number;
  state: "pending" | "running" | "validated" | "failed" | "cancelled" | "timed_out";
  reportPreview?: string | null;
  streamPreview?: string | null;
  thinkingPreview?: string | null;
  aiActivity?: AIActivity | null;
}

export interface ReportGeneration {
  language?: "ro" | "en";
  jobId: string;
  searchId: string;
  state: "accepted" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out";
  stage: string;
  provider: string;
  model: string;
  createdAt: number;
  startedAt?: number | null;
  deadlineAt: number;
  reportId?: string | null;
  partial?: boolean;
  errorCode?: string | null;
  message?: string | null;
  workerActive?: boolean;
  queuePosition?: number | null;
  streamPreview?: string | null;
  reportPreview?: string | null;
  previewVersion?: number;
  batchesCompleted?: number;
  batchesTotal?: number;
  batchPreviews?: ReportBatchPreview[];
  thinkingPreview?: string | null;
  streamTokensPerSecond?: number | null;
  thinkingTokensPerSecond?: number | null;
  aiActivity?: AIActivity | null;
}

export interface CategoriesResponse {
  indexGeneration: string | null;
  tree: CategoryNode | null;
  defaultSelection: string[];
}

export interface ResourceInvalidations {
  evictedSearchIds?: string[];
  evictedReportIds?: string[];
  evictedGroupIds?: string[];
  cancelled?: boolean;
}

export interface MessagesResponse extends ResourceInvalidations {
  indexGeneration?: string;
  removedCategoryIds?: string[];
  messages: ChatMessage[];
}

export interface SendMessageResponse extends ResourceInvalidations {
  messages: ChatMessage[];
  // True when POST /api/search should be called next to actually run
  // retrieval — kept as a separate, slower call so the echo/notice above
  // render immediately instead of waiting for the search to finish too.
  startSearch: boolean;
  // True when POST /api/condition should be called first: the dictionary does
  // not know the condition, so the AI is asked for it before the search starts.
  identifyCondition?: boolean;
  contextRevision?: number;
  classifyMessage?: boolean;
}

export interface ClassificationResponse extends SendMessageResponse {
  intent?: "remedii" | "planta" | "diverse" | "email_raport" | "top_plante";
}

export interface ConditionResponse extends ResourceInvalidations {
  messages: ChatMessage[];
  startSearch: boolean;
}

export interface GenerateResponse extends ResourceInvalidations {
  partial: boolean;
  validationWarnings: { code: string; section?: string | null; index?: number | null; count?: number | null }[];
  messages: ChatMessage[];
  ownerNotice: string | null;
}
