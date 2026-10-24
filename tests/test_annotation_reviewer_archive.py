import json
from pathlib import Path
import tempfile
import unittest
from scripts.archive_annotation_by_reviewer import archive


class ReviewerArchiveTests(unittest.TestCase):
    def test_group_sessions_preserve_revisions_and_escape_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'receipts'; output=root/'archive'
            for session, revisions in [('one',[1,2]),('two',[1])]:
                folder=source/session; folder.mkdir(parents=True)
                for revision in revisions:
                    (folder/f'{revision}.json').write_text(json.dumps({'reviewer_alias':'../../<script>alert(1)</script>', 'revision':revision,'answers':{'q':'<unsafe>'},'status':'in_progress'}))
            before={p:p.read_bytes() for p in source.glob('*/*.json')}
            self.assertEqual(archive(source,output),{'reviewers':1,'sessions':2,'unreadable_receipts':0})
            self.assertEqual(len(list(output.glob('reviewers/*/*/versions/*.json'))),3)
            text=(output/'index.html').read_text()
            self.assertNotIn('<script>',text);self.assertIn('&lt;unsafe&gt;',text)
            archive(source,output)
            self.assertEqual(before,{p:p.read_bytes() for p in source.glob('*/*.json')})
            path=source/'one'/'1.json';path.write_text(path.read_text().replace('in_progress','submitted'))
            with self.assertRaisesRegex(ValueError,'revision changed'):
                archive(source,output)


if __name__=='__main__':
    unittest.main()
