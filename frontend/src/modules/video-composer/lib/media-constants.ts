export const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v']);

export const VIDEO_PICKER_FILTERS = [
  {
    name: 'Video',
    extensions: [...VIDEO_EXTENSIONS],
  },
];

export function isVideoPath(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  return VIDEO_EXTENSIONS.has(ext);
}
