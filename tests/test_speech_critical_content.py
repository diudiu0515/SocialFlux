"""Critical speech facts survive ASR spelling differences without numeric drift."""
import unittest

from scripts.screen_annotation400_av import critical_content_matches


class CriticalSpeechTest(unittest.TestCase):
    def test_clock_notation_preserves_hour_and_minute(self):
        for hour, number in [('one', 1), ('three', 3), ('five', 5), ('twelve', 12)]:
            for minute, digits in [('ten', 10), ('seventeen', 17), ('twenty-five', 25),
                                   ('thirty', 30), ('forty-two', 42), ('fifty-nine', 59)]:
                for separator in [':', '.', ', ']:
                    with self.subTest(hour=hour, minute=minute, separator=separator):
                        self.assertTrue(critical_content_matches(
                            f'Send it by {hour}-{minute}, not later.',
                            f'Send it by {number}{separator}{digits:02}, not later.'))

    def test_changed_or_concatenated_times_are_rejected(self):
        for observed in ['Send it by 4.30.', 'Send it by 3.40.', 'Send it by 330.',
                         'Send it by 3.3.', 'Send it by 3.30 and 4.00.']:
            self.assertFalse(critical_content_matches('Send it by three-thirty.', observed))

    def test_numeric_clock_with_asr_comma_keeps_exact_values(self):
        self.assertTrue(critical_content_matches('Close at 7:28 after 6:18.',
                                                'Close at 7, 28 after 6, 18.'))
        self.assertFalse(critical_content_matches('Close at 7:28.', 'Close at 7 and 28.'))
        self.assertFalse(critical_content_matches('Close at 7:28.', 'Close at 7, 29.'))

    def test_decimal_quantities_do_not_become_clocks(self):
        self.assertTrue(critical_content_matches('The cost is 3.30.', 'The cost is 3.30.'))
        self.assertFalse(critical_content_matches('The cost is 3.30.', 'The cost is 3:30.'))
        self.assertFalse(critical_content_matches('The cost is 3.30.', 'The cost is 330.'))
        self.assertFalse(critical_content_matches('Use three, thirty, and four.', 'Use 3.30 and 4.'))

    def test_negations_and_numeric_order_are_retained(self):
        self.assertTrue(critical_content_matches("Don't release the two records.",
                                                'Do not release the 2 records.'))
        for observed in ['Release the 2 records.', 'Do not release the 3 records.',
                         'Do not release the records.']:
            self.assertFalse(critical_content_matches("Don't release the two records.", observed))
        self.assertFalse(critical_content_matches('Start at 3:30 and end at 5:30.',
                                                 'Start at 5:30 and end at 3:30.'))


if __name__ == '__main__':
    unittest.main()
