"""Generate the sample document the demo evaluation dataset is written against.

    python manage.py make_demo_corpus

Produces a policy handbook PDF with one topic per page and specific, checkable
facts — exact figures, named tiers, real durations. That shape is what makes an
evaluation dataset possible at all: "the refund window is 30 days for domestic
orders and 45 for international" has a right answer and a page it lives on,
so recall, citation validity and correctness are all measurable rather than
matters of opinion.

Written with reportlab, which is already a dependency for the chat PDF export,
so this adds nothing to the install.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_NAME = 'northwind_customer_policy.pdf'

# One page per topic. Retrieval quality is easy to reason about when a fact
# lives on exactly one page, and the dataset's expected_pages can then be exact.
PAGES = [
    (
        'Northwind Retail — Customer Policy Handbook',
        [
            'Revision 7.2, effective 1 March 2026.',
            '',
            'This handbook sets out the policies governing purchases, returns, '
            'shipping, warranty and support for all Northwind Retail customers.',
            '',
            'Contents',
            '  Page 2   Refunds and Returns',
            '  Page 3   Shipping and Delivery',
            '  Page 4   Product Warranty',
            '  Page 5   Damaged and Incorrect Items',
            '  Page 6   Data Retention and Privacy',
            '  Page 7   Customer Support',
            '  Page 8   Loyalty Programme',
            '',
            'Questions about this handbook should be directed to the Customer '
            'Operations team.',
        ],
    ),
    (
        'Refunds and Returns',
        [
            'Domestic orders may be returned for a full refund within 30 days of '
            'the delivery date.',
            '',
            'International purchases have a longer window of 45 days, measured from '
            'the date the carrier records delivery in the destination country.',
            '',
            'A restocking fee of 15% applies to opened items returned without a '
            'manufacturing fault. Unopened items are never subject to a restocking '
            'fee.',
            '',
            'Refunds are issued to the original payment method and take between 5 '
            'and 10 business days to appear, depending on the issuing bank.',
            '',
            'Items purchased during a clearance event are final sale and cannot be '
            'returned unless faulty.',
            '',
            'Return shipping is paid by the customer except where the item is '
            'faulty, damaged in transit, or was sent in error.',
        ],
    ),
    (
        'Shipping and Delivery',
        [
            'Standard delivery takes 5 to 7 business days and costs 4.99 GBP.',
            '',
            'Express delivery arrives within 2 business days and costs 12.99 GBP. '
            'Orders placed after 14:00 are dispatched the following business day.',
            '',
            'Standard delivery is free on all orders over 75 GBP.',
            '',
            'International shipping is available to 42 countries. Delivery takes 7 '
            'to 21 business days and any import duty is the responsibility of the '
            'recipient.',
            '',
            'Northwind Retail does not deliver to PO boxes or freight-forwarding '
            'addresses.',
            '',
            'A tracking number is issued by email once the parcel leaves the '
            'distribution centre in Reading.',
        ],
    ),
    (
        'Product Warranty',
        [
            'All products carry a standard manufacturer warranty of 24 months from '
            'the date of purchase.',
            '',
            'Customers who register a product within 60 days of purchase receive an '
            'extended warranty of 36 months at no additional cost.',
            '',
            'The warranty covers manufacturing defects and component failure under '
            'normal use. It does not cover accidental damage, liquid ingress, '
            'cosmetic wear, or damage caused by unauthorised repair.',
            '',
            'Warranty claims require proof of purchase. An order number is '
            'sufficient; a printed receipt is not required.',
            '',
            'Where a product cannot be repaired, Northwind Retail will replace it '
            'with an equivalent model. Where no equivalent exists, a credit note '
            'for the original purchase price is issued.',
        ],
    ),
    (
        'Damaged and Incorrect Items',
        [
            'Damage in transit must be reported within 7 days of delivery.',
            '',
            'Reports must include at least two photographs: one of the item and one '
            'of the outer packaging as received.',
            '',
            'Incorrect items should not be returned before contacting support. A '
            'prepaid return label is issued once the error is confirmed, usually '
            'within one business day.',
            '',
            'Replacements for damaged items are dispatched by express delivery at '
            'no cost to the customer.',
            '',
            'Claims made after the 7 day window may still be considered where the '
            'damage could not reasonably have been discovered earlier, at the '
            'discretion of the Customer Operations team.',
        ],
    ),
    (
        'Data Retention and Privacy',
        [
            'Order records are retained for 24 months after the final interaction '
            'on the account, after which they are anonymised.',
            '',
            'Payment card details are never stored by Northwind Retail. Card data '
            'is handled entirely by the payment processor.',
            '',
            'Customers may request a copy of their personal data at any time. '
            'Requests are fulfilled within 30 days.',
            '',
            'Marketing consent is opt-in and can be withdrawn from the account '
            'settings page or by replying STOP to any message.',
            '',
            'The Data Protection Officer can be reached at privacy@northwind-'
            'retail.example.',
        ],
    ),
    (
        'Customer Support',
        [
            'Support is available Monday to Friday, 09:00 to 18:00 GMT, excluding '
            'public holidays.',
            '',
            'Tickets receive a first response within 4 business hours. Complex '
            'cases are escalated to a specialist within one business day.',
            '',
            'Live chat is available during support hours. Email is monitored '
            'continuously but answered during support hours only.',
            '',
            'A complaint that cannot be resolved by the support team is escalated '
            'to the Customer Operations manager, who responds within 5 business '
            'days.',
            '',
            'Support is provided in English, French and German.',
        ],
    ),
    (
        'Loyalty Programme',
        [
            'Customers earn 1 point for every 1 GBP spent, excluding delivery '
            'charges.',
            '',
            'The programme has three tiers. Silver begins at 500 points, Gold at '
            '2,000 points, and Platinum at 5,000 points.',
            '',
            'Silver members receive free standard delivery. Gold members '
            'additionally receive early access to sales. Platinum members receive '
            'free express delivery and a dedicated support line.',
            '',
            'Points expire 18 months after they are earned if the account has had '
            'no qualifying purchase in that period.',
            '',
            'Tier status is reviewed every 12 months and does not decrease by more '
            'than one tier at a review.',
        ],
    ),
]


class Command(BaseCommand):
    help = 'Generate the sample policy PDF the demo evaluation dataset is written against.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default='',
                            help=f'Output path (default: <BASE_DIR>/evaluation/corpus/{DEFAULT_NAME})')

    def handle(self, *args, **opts):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
        except ImportError as exc:
            raise CommandError('reportlab is required. pip install -r requirements.txt') from exc

        destination = Path(opts['out']) if opts['out'] else (
            Path(settings.BASE_DIR) / 'evaluation' / 'corpus' / DEFAULT_NAME
        )
        destination.parent.mkdir(parents=True, exist_ok=True)

        page_width, page_height = A4
        pdf = canvas.Canvas(str(destination), pagesize=A4)
        pdf.setTitle('Northwind Retail — Customer Policy Handbook')

        left = 25 * mm
        right = page_width - 25 * mm
        wrap_width = right - left

        for index, (heading, paragraphs) in enumerate(PAGES, start=1):
            y = page_height - 30 * mm

            pdf.setFont('Helvetica-Bold', 17 if index == 1 else 15)
            pdf.drawString(left, y, heading)
            y -= 4 * mm
            pdf.setLineWidth(0.6)
            pdf.line(left, y, right, y)
            y -= 9 * mm

            pdf.setFont('Helvetica', 11)
            for paragraph in paragraphs:
                if not paragraph:
                    y -= 4 * mm
                    continue
                for line in _wrap(pdf, paragraph, wrap_width, 'Helvetica', 11):
                    pdf.drawString(left, y, line)
                    y -= 5.6 * mm
                y -= 1.5 * mm

            # Page number in the footer: the extractor records page numbers
            # itself, but a visible one makes a citation checkable by hand.
            pdf.setFont('Helvetica-Oblique', 9)
            pdf.drawCentredString(page_width / 2, 15 * mm, f'Page {index}')
            pdf.showPage()

        pdf.save()

        self.stdout.write(self.style.SUCCESS(f'Wrote {destination}'))
        self.stdout.write(
            f'  {len(PAGES)} pages, one topic each.\n\n'
            'Next:\n'
            '  1. Upload it through the app (or the API) and wait for processing.\n'
            '  2. python manage.py load_eval_dataset\n'
            '  3. python manage.py evaluate_rag --label baseline\n'
        )


def _wrap(pdf, text: str, width: float, font: str, size: int) -> list[str]:
    """Greedy word wrap against the real rendered width of the font."""
    words = text.split()
    lines: list[str] = []
    current = ''

    for word in words:
        candidate = f'{current} {word}'.strip()
        if pdf.stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)
    return lines
