"""
Receipt generation service — creates PDF receipts for successful payments.
"""

import io
import logging
import uuid
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptResponse
from app.utils.exceptions import NotFoundError, PaymentError

logger = logging.getLogger(__name__)


class ReceiptService:
    """Generates and stores PDF receipts."""

    async def get_or_create_receipt(
        self, db: AsyncSession, payment_id: uuid.UUID
    ) -> tuple[ReceiptResponse, bytes]:
        """Get existing receipt or generate a new one."""
        # Check for existing receipt
        result = await db.execute(
            select(Receipt).where(Receipt.payment_id == payment_id)
        )
        existing = result.scalar_one_or_none()
        if existing and existing.pdf_data:
            return self._to_response(existing), existing.pdf_data

        # Get the payment
        result = await db.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        if not payment:
            raise NotFoundError("Payment", str(payment_id))

        if payment.status != PaymentStatus.SUCCEEDED:
            raise PaymentError(
                f"Receipts can only be generated for succeeded payments. "
                f"Current status: {payment.status.value}"
            )

        # Generate PDF
        pdf_data = self._generate_pdf(payment)

        # Generate receipt number
        receipt_number = f"RCP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Persist
        receipt = Receipt(
            payment_id=payment_id,
            receipt_number=receipt_number,
            pdf_data=pdf_data,
        )
        db.add(receipt)
        await db.flush()
        await db.refresh(receipt)

        logger.info(f"Receipt generated: {receipt_number} for payment {payment_id}")
        return self._to_response(receipt), pdf_data

    def _generate_pdf(self, payment: Payment) -> bytes:
        """Generate a professional PDF receipt."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=25 * mm,
            leftMargin=25 * mm,
            topMargin=25 * mm,
            bottomMargin=25 * mm,
        )

        styles = getSampleStyleSheet()
        elements = []

        # Custom styles
        title_style = ParagraphStyle(
            "ReceiptTitle",
            parent=styles["Title"],
            fontSize=24,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a2e"),
        )
        heading_style = ParagraphStyle(
            "ReceiptHeading",
            parent=styles["Heading2"],
            fontSize=14,
            spaceAfter=8,
            textColor=colors.HexColor("#16213e"),
        )
        body_style = ParagraphStyle(
            "ReceiptBody",
            parent=styles["Normal"],
            fontSize=11,
            spaceAfter=4,
            textColor=colors.HexColor("#333333"),
        )
        small_style = ParagraphStyle(
            "ReceiptSmall",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#666666"),
        )

        # ── Header ──
        elements.append(Paragraph("PAYMENT RECEIPT", title_style))
        elements.append(
            HRFlowable(
                width="100%", thickness=2, color=colors.HexColor("#4361ee"), spaceAfter=12
            )
        )

        # ── Payment Details ──
        elements.append(Paragraph("Payment Details", heading_style))

        amount_display = f"${payment.amount / 100:.2f} {payment.currency.upper()}"
        created = payment.created_at.strftime("%B %d, %Y at %H:%M UTC") if payment.created_at else "N/A"

        details_data = [
            ["Payment ID", str(payment.id)],
            ["Amount", amount_display],
            ["Status", payment.status.value.upper()],
            ["Date", created],
        ]

        if payment.description:
            details_data.append(["Description", payment.description])
        if payment.stripe_payment_intent_id:
            details_data.append(["Reference", payment.stripe_payment_intent_id])
        if payment.payment_method_id:
            details_data.append(["Payment Method", payment.payment_method_id])

        details_table = Table(details_data, colWidths=[120, 350])
        details_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#16213e")),
                    ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#333333")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#e0e0e0")),
                ]
            )
        )
        elements.append(details_table)
        elements.append(Spacer(1, 20))

        # ── Refund info if applicable ──
        if payment.amount_refunded > 0:
            elements.append(Paragraph("Refund Information", heading_style))
            refund_data = [
                ["Amount Refunded", f"${payment.amount_refunded / 100:.2f} {payment.currency.upper()}"],
                ["Net Amount", f"${(payment.amount - payment.amount_refunded) / 100:.2f} {payment.currency.upper()}"],
            ]
            refund_table = Table(refund_data, colWidths=[120, 350])
            refund_table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(refund_table)
            elements.append(Spacer(1, 20))

        # ── Footer ──
        elements.append(
            HRFlowable(
                width="100%", thickness=1, color=colors.HexColor("#e0e0e0"), spaceAfter=8
            )
        )
        elements.append(
            Paragraph(
                "This is an automatically generated receipt. "
                "For questions or disputes, please contact support.",
                small_style,
            )
        )
        elements.append(
            Paragraph(
                f"Generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}",
                small_style,
            )
        )

        doc.build(elements)
        return buffer.getvalue()

    @staticmethod
    def _to_response(receipt: Receipt) -> ReceiptResponse:
        return ReceiptResponse(
            id=receipt.id,
            payment_id=receipt.payment_id,
            receipt_number=receipt.receipt_number,
            created_at=receipt.created_at,
        )


# Singleton
receipt_service = ReceiptService()
