"""PII Recall test — hand-labeled synthetic document with known PII instances."""

from app.services.pii_service import detect_pii

# Hand-labeled test document with known PII instances
TEST_DOC = """
Contact Information:
- Email: john.doe@example.com
- Email: jane.smith@company.org
- Phone: +1-555-123-4567
- Phone: (555) 987-6543
- SSN: 123-45-6789
- ID: AB1234567

Non-PII content:
- Not an email: user at example dot com
- Not a phone: 555-1234 (missing area code)
- Not an SSN: 12-345-6789
"""

# Ground truth counts
GROUND_TRUTH = {
    "email": 2,
    "phone_number": 2,
    "id_number": 2,  # SSN + ID
}

def compute_recall():
    detected = detect_pii(TEST_DOC)
    
    print("=== PII Recall Test ===")
    print(f"Ground truth: {GROUND_TRUTH}")
    print(f"Detected:     {detected}")
    
    total_gt = sum(GROUND_TRUTH.values())
    total_detected = sum(detected.values())
    
    # True positives: min(detected, ground_truth) per type
    true_positives = sum(min(detected.get(k, 0), GROUND_TRUTH[k]) for k in GROUND_TRUTH)
    
    recall = true_positives / total_gt if total_gt > 0 else 0
    
    print(f"\nPer-type:")
    for pii_type in GROUND_TRUTH:
        gt = GROUND_TRUTH[pii_type]
        det = detected.get(pii_type, 0)
        tp = min(det, gt)
        r = tp / gt if gt > 0 else 0
        print(f"  {pii_type:12s}: GT={gt}, Detected={det}, TP={tp}, Recall={r:.2f}")
    
    print(f"\nOverall Recall: {recall:.4f} ({true_positives}/{total_gt})")
    
    # Precision
    precision = true_positives / total_detected if total_detected > 0 else 0
    print(f"Overall Precision: {precision:.4f} ({true_positives}/{total_detected})")
    
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    print(f"F1 Score: {f1:.4f}")

if __name__ == "__main__":
    compute_recall()