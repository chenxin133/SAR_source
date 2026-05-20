export interface SarImage {
  id: string;
  name: string;
  satellite: string;
  acquisitionDate: string; // ISO String
  fileSize: string;
  resolution?: string;
  polarization?: string; // HH, HV, VH, VV
  status: string; // 'Uploading' | 'Processing' | 'Ready' | 'Error';
  description?: string;
  thumbnailUrl?: string; // Mock URL
  previewUrl?: string; // URL for full size preview
  previewPersistent?: boolean;
  originalPersistent?: boolean;
  previewNotice?: string;
}

export interface UploadPayload {
  name: string;
  satellite: string;
  file: File;
  description?: string;
  polarization?: string;
  resolution?: string;
}
