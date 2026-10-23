import retired from '../data/retired-media.json';

const files = new Set<string>(retired.files);
export function mediaRetired(url: string) {
  return url.startsWith('/media/') && files.has(url.slice('/media/'.length));
}
