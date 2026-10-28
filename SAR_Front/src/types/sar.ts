export interface SarImage {
  id: string;
  name: string;
  satellite: string;
  acquisitionDate: string; // ISO String
  fileSize: string;
  sizeBytes?: number;
  resolution?: string;
  frequencyBand?: string; // Ka, Ku, X, C
  polarization?: string; // Single, dual, or quad polarization combination
  width?: number;
  height?: number;
  status: string; // 'Uploading' | 'Processing' | 'Ready' | 'Error';
  description?: string;
  thumbnailUrl?: string; // Mock URL
  previewUrl?: string; // URL for full size preview
  previewPersistent?: boolean;
  originalPersistent?: boolean;
  previewNotice?: string;
  errorMessage?: string;
}

export type ImageMetadataPatch = Partial<Pick<SarImage,
  'name' | 'satellite' | 'acquisitionDate' | 'sizeBytes' | 'fileSize' |
  'resolution' | 'frequencyBand' | 'polarization' | 'description' | 'status' | 'errorMessage'
>>;

export interface UploadPayload {
  name: string;
  satellite: string;
  file: File;
  acquisitionAt?: string;
  description?: string;
  frequencyBand?: string;
  polarization?: string;
  resolution?: string;
}
