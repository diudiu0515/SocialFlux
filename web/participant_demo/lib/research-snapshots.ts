export type MediaSnapshot = {
  release: string; dataset_sha256: string; source_bank_sha256: string;
  assignments: any[];
  items: {id: string; item_sha256: string; has_video: boolean; media: any[]; coverage: unknown}[];
};
type FrozenResearch = {
  release: string; dataset_sha256: string; source_bank_sha256: string;
  assignments: any[];
  items: {id: string; item_sha256: string; public_text: any; public_video: any; media: any[]; coverage: unknown}[];
};

export function restoreMediaSnapshot<T extends FrozenResearch>(current: T, snapshot: MediaSnapshot): T {
  if (snapshot.source_bank_sha256 !== current.source_bank_sha256) throw new Error('English snapshot source changed');
  const rows = new Map(snapshot.items.map(row => [row.id, row]));
  if (rows.size !== snapshot.items.length || rows.size !== current.items.length) throw new Error('English snapshot item count changed');
  const items = current.items.map(item => {
    const old = rows.get(item.id);
    if (!old || old.item_sha256 !== item.item_sha256) throw new Error('English snapshot item changed');
    return {...item, public_video: old.has_video ? {...item.public_text, modality: 'text+video'} : null,
      media: old.media, coverage: old.coverage};
  });
  return {...current, release: snapshot.release, dataset_sha256: snapshot.dataset_sha256,
    assignments: snapshot.assignments, items};
}
