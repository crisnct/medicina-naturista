export interface GenerationFeedback {
  message: string;
  requiresAuthorization?: boolean;
  progress?: string;
  cancel?: () => void;
}
