
export enum GenerationStatus {
  IDLE = 'IDLE',
  GENERATING = 'GENERATING',
  SUCCESS = 'SUCCESS',
  ERROR = 'ERROR',
}

export interface GenerationState {
  status: GenerationStatus;
  videoUrl?: string;
  error?: string;
}
