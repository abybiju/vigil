"""Hand-authored, leak-free eval dataset. Run once to emit eval/dataset.csv.

Labels are assigned from the rubric (eval/rubric.md) + authoring intent, NOT from any model.
The adversarial bucket (B5) is fully hand-written. Keep each message single-line.

Columns emitted: id, bucket, journey_stage, order_ref, text,
gold_is_complaint, gold_clinical_red_flag, gold_potential_mdr, gold_severity, notes
"""

from __future__ import annotations

import csv
from pathlib import Path

# Each tuple: (journey_stage, text, is_complaint, clinical_red_flag, potential_mdr, severity, notes)
B1_NON_COMPLAINTS = [
    ("pre_kit", "Hi, when will my impression kit arrive? I ordered a couple days ago.", False, False, False, "none", "tracking"),
    ("unknown", "Can I use two promo codes together at checkout?", False, False, False, "none", "discount"),
    ("unknown", "How long does treatment usually take on average?", False, False, False, "none", "how-it-works"),
    ("unknown", "Do you ship to Alaska and Hawaii?", False, False, False, "none", "shipping info"),
    ("unknown", "Whats the difference between the day and night aligner plans?", False, False, False, "none", "product info"),
    ("in_treatment", "Can I change the payment method on my monthly plan?", False, False, False, "none", "billing mechanics"),
    ("unknown", "Is there a student or military discount available?", False, False, False, "none", "discount"),
    ("post_impression", "How do I track my order once it ships?", False, False, False, "none", "tracking"),
    ("pre_kit", "What exactly is included in the impression kit?", False, False, False, "none", "info, not a defect"),
    ("unknown", "Do I need to see a dentist in person before starting?", False, False, False, "none", "process"),
    ("in_treatment", "Can I pause my monthly payments for one month?", False, False, False, "none", "billing"),
    ("post_impression", "When will I get my 3D treatment preview to approve?", False, False, False, "none", "process"),
    ("pre_kit", "Any tips for taking good impressions the first time?", False, False, False, "none", "how-to"),
    ("unknown", "Are retainers included after I finish treatment?", False, False, False, "none", "product info"),
    ("post_impression", "My tracking shows delivery tomorrow, can I update the address?", False, False, False, "none", "logistics"),
    ("unknown", "How much does the night aligner plan cost?", False, False, False, "none", "pricing"),
    ("unknown", "Do you offer financing or a payment plan?", False, False, False, "none", "financing"),
    ("in_treatment", "How often am I supposed to switch to the next set of trays?", False, False, False, "none", "instructions"),
    ("unknown", "I was double-charged on my card for one order, can you check?", False, False, False, "none", "billing error, not a device complaint"),
    ("unknown", "Can I order an extra storage case for travel?", False, False, False, "none", "upsell request"),
]

B2_COMPLAINTS_NON_CLINICAL = [
    ("pre_kit", "My impression kit arrived with the putty already hardened, I cant use it.", True, False, False, "none", "quality defect"),
    ("post_impression", "The app keeps crashing every time I try to upload my impression photos.", True, False, False, "none", "app performance"),
    ("in_treatment", "I got the wrong aligner step, the bag says step 9 but Im only on step 4.", True, False, False, "none", "fulfillment defect"),
    ("pre_kit", "One of the impression trays was missing from my kit.", True, False, False, "none", "missing part"),
    ("in_treatment", "My aligner storage case cracked in half after about a week.", True, False, False, "none", "durability, accessory"),
    ("preview_approved", "My aligners arrived with a crack in one of the trays, right out of the package.", True, False, False, "none", "device durability, no injury"),
    ("pre_kit", "The kit shipped without the prepaid return mailer for my impressions.", True, False, False, "none", "missing part"),
    ("preview_approved", "I paid for both arches but only received upper aligners.", True, False, False, "none", "fulfillment"),
    ("post_treatment", "My retainer came with a visible scratch across the front.", True, False, False, "none", "cosmetic quality"),
    ("post_impression", "The app wont let me log in, it says my account doesnt exist.", True, False, False, "none", "app performance"),
    ("in_treatment", "These night aligners feel identical to the last step, like nothing changed.", True, False, False, "none", "performance, no symptom"),
    ("pre_kit", "The instruction guide in my kit was for a totally different product.", True, False, False, "none", "quality"),
    ("pre_kit", "The chewies that came with my kit are clearly the wrong size.", True, False, False, "none", "wrong accessory"),
    ("in_treatment", "My next set of trays never arrived even though the app says shipped.", True, False, False, "none", "fulfillment/quality complaint"),
    ("preview_approved", "The treatment preview shows the wrong name and case, this isnt mine.", True, False, False, "none", "data/quality error"),
    ("pre_kit", "Half the putty packets in my kit were torn open and dried out.", True, False, False, "none", "quality defect"),
    ("in_treatment", "The print on my aligner pouch is smudged so I cant read the step number.", True, False, False, "none", "labeling quality"),
    ("post_treatment", "My retainer case latch broke the second day I had it.", True, False, False, "none", "accessory durability"),
    ("in_treatment", "I was sent someone elses order, the packing slip has a different address.", True, False, False, "none", "fulfillment error"),
]

B3_CLINICAL_NON_SERIOUS = [
    ("in_treatment", "The new tray is rubbing a little sore spot on my gum, kind of annoying.", True, True, False, "minor", "minor soft tissue"),
    ("in_treatment", "Theres a slightly rough edge on this aligner thats poking my cheek.", True, True, False, "minor", "rough edge, minor"),
    ("in_treatment", "My gums feel a bit tender around the front teeth with this set.", True, True, False, "minor", "mild tenderness"),
    ("in_treatment", "My teeth are a little more sore than I expected after switching yesterday.", True, True, False, "minor", "mild pain, slightly beyond expected"),
    ("in_treatment", "One tooth feels a bit sensitive to cold since I started this step.", True, True, False, "minor", "mild sensitivity"),
    ("in_treatment", "The aligner pinches my gum a little when I first seat it.", True, True, False, "minor", "minor pinch"),
    ("in_treatment", "I get a mild ache in my jaw after wearing them a few hours.", True, True, False, "minor", "mild jaw ache"),
    ("in_treatment", "Theres a little redness on my gum right where the tray edge sits.", True, True, False, "minor", "minor irritation"),
    ("in_treatment", "A small spot inside my lip feels raw from the tray, nothing bad.", True, True, False, "minor", "minor soft-tissue rub"),
    ("in_treatment", "My front teeth feel slightly tender when I press on them, mild.", True, True, False, "minor", "mild tenderness"),
    ("in_treatment", "This step makes my teeth ache a bit more than the last, still manageable.", True, True, False, "minor", "mild pain"),
    ("in_treatment", "The tray feels really tight and a little uncomfortable on day one.", True, True, False, "minor", "tightness/discomfort"),
    ("in_treatment", "I have a tiny bit of gum soreness, like a mild rub, since the new trays.", True, True, False, "minor", "mild soreness"),
    ("in_treatment", "My cheek is a little irritated where the aligner edge touches.", True, True, False, "minor", "minor irritation"),
    ("in_treatment", "Slight sensitivity when I drink something cold with the new set in.", True, True, False, "minor", "mild sensitivity"),
    ("in_treatment", "My gums are a touch sore but it eases after an hour or so.", True, True, False, "minor", "transient mild soreness"),
    ("in_treatment", "The bottom tray rubs the inside of my lip a little, minor annoyance.", True, True, False, "minor", "minor rub"),
    ("in_treatment", "Mild dull ache in a couple teeth after switching, not too bad.", True, True, False, "minor", "mild pain"),
    ("in_treatment", "I notice a little tenderness on the gum line, pretty mild though.", True, True, False, "minor", "mild tenderness"),
]

B4_CLINICAL_SERIOUS = [
    ("in_treatment", "One of my bottom front teeth feels loose now after this step, Im worried.", True, True, True, "serious", "tooth mobility"),
    ("in_treatment", "Ive had severe throbbing pain for three days and I cant eat on that side.", True, True, True, "serious", "severe persistent pain + dysfunction"),
    ("in_treatment", "My gum is really swollen and puffy around a back tooth since wearing these.", True, True, True, "serious", "swelling"),
    ("in_treatment", "My gums have started receding and I can see more of the tooth root now.", True, True, True, "serious", "gum recession"),
    ("in_treatment", "I think Im having an allergic reaction, my lips are swollen and itchy.", True, True, True, "serious", "allergic reaction, systemic"),
    ("in_treatment", "The tray edge cut my gum and its bleeding a lot, wont stop.", True, True, True, "serious", "laceration + bleeding"),
    ("in_treatment", "My gums have been bleeding every day for over a week now.", True, True, True, "serious", "persistent bleeding"),
    ("in_treatment", "My bite feels totally off, my back teeth dont meet anymore.", True, True, True, "serious", "bite change/malocclusion"),
    ("in_treatment", "Part of my lower lip feels numb and tingly since I started this set.", True, True, True, "serious", "numbness/paresthesia"),
    ("in_treatment", "Theres pus and a really bad taste coming from one tooth, and it aches.", True, True, True, "serious", "infection signs"),
    ("in_treatment", "Two of my teeth feel wobbly and one even shifted, this scares me.", True, True, True, "serious", "mobility"),
    ("in_treatment", "My jaw is swollen on one side and it hurts to open my mouth.", True, True, True, "serious", "swelling + pain"),
    ("in_treatment", "I broke out in hives on my face and my mouth is burning with these in.", True, True, True, "serious", "allergic reaction"),
    ("in_treatment", "A tray cracked and a sharp piece sliced the inside of my cheek open.", True, True, True, "serious", "device malfunction + laceration"),
    ("in_treatment", "The pain is so bad I havent slept in two nights and ibuprofen isnt helping.", True, True, True, "serious", "severe pain"),
    ("in_treatment", "One tooth has gone grey and really hurts, I think something is wrong.", True, True, True, "serious", "possible nerve damage"),
    ("in_treatment", "My gum is swollen, bleeding, and theres a lump that wasnt there before.", True, True, True, "serious", "swelling + bleeding + lesion"),
    ("in_treatment", "My front tooth feels like it could come out, it moves when I touch it.", True, True, True, "serious", "severe mobility"),
    ("in_treatment", "Ever since this step my face is swollen and Im running a slight fever.", True, True, True, "serious", "swelling + systemic"),
]

B5_ADVERSARIAL = [
    ("in_treatment", "While I have you, can you fix my autopay? Also one of my back teeth feels a bit loose now.", True, True, True, "serious", "buried red flag in billing"),
    ("in_treatment", "Its probably nothing and Im sure its fine, but my gum has been bleeding for a week.", True, True, True, "serious", "downplayed harm"),
    ("in_treatment", "love that my jaw clicks and locks up now lol, anyway when does my next set ship?", True, True, True, "serious", "sarcasm hiding bite/jaw issue"),
    ("in_treatment", "I want a refund AND someone to explain why my face is swollen after wearing these.", True, True, True, "serious", "mixed billing + clinical"),
    ("unknown", "Honestly this price is killing me, can I get a discount?", False, False, False, "none", "idiom, no real symptom"),
    ("unknown", "My tooth is gonna fall out if I have to pay this bill lol, can you waive the late fee?", False, False, False, "none", "idiom in billing, not clinical"),
    ("in_treatment", "Just confirming the day-two pressure and mild soreness is normal, right? No big deal.", False, False, False, "minor", "expected-soreness decoy, crf F"),
    ("in_treatment", "Asking for my sister who uses these, her gum is really swollen and bleeding, what should she do?", True, True, True, "serious", "third-person serious red flag"),
    ("in_treatment", "Worst aligners ever, they hurt so bad I had to stop wearing them after a week.", True, True, True, "serious", "venting review, severe pain"),
    ("in_treatment", "My bite feels a little off lately, is that something to worry about?", True, True, False, "moderate", "ambiguous bite change, question"),
    ("in_treatment", "A tooth feels slightly loose but thats probably normal with aligners, right?", True, True, True, "serious", "downplayed mobility"),
    ("in_treatment", "The aligners taste really weird and my mouth feels kind of funny and tingly.", True, True, True, "serious", "possible reaction, ambiguous -> flag"),
    ("unknown", "Your shipping is painfully slow and it makes me want to scream, where is my kit?", False, False, False, "none", "emotional idiom, shipping only"),
    ("in_treatment", "Quick billing question about my plan, oh and is some gum bleeding normal when I brush with them in?", True, True, True, "serious", "buried bleeding question"),
    ("in_treatment", "My retainer cracked and also my gum has been swollen for a few days.", True, True, True, "serious", "device defect + clinical"),
    ("in_treatment", "Everything is basically fine, just FYI a front tooth feels loose, no rush at all.", True, True, True, "serious", "minimized serious mobility"),
    ("in_treatment", "great, now my gums bleed every single time I take these out, 10/10 experience.", True, True, True, "serious", "sarcasm, real bleeding"),
    ("in_treatment", "I think Im allergic, my lips feel tingly and a bit swollen, but maybe its nothing.", True, True, True, "serious", "downplayed allergic reaction"),
    ("in_treatment", "Can I switch to night aligners? These day ones make my teeth ache way too much to function.", True, True, False, "moderate", "request + notable pain, not clearly serious"),
    ("unknown", "This whole process has been a headache, I just want to know my refund status.", False, False, False, "none", "idiom headache, billing/status only"),
]

BUCKETS = [
    ("B1_non_complaint", B1_NON_COMPLAINTS),
    ("B2_complaint_non_clinical", B2_COMPLAINTS_NON_CLINICAL),
    ("B3_clinical_non_serious", B3_CLINICAL_NON_SERIOUS),
    ("B4_clinical_serious", B4_CLINICAL_SERIOUS),
    ("B5_adversarial", B5_ADVERSARIAL),
]

FIELDS = [
    "id", "bucket", "journey_stage", "order_ref", "text",
    "gold_is_complaint", "gold_clinical_red_flag", "gold_potential_mdr", "gold_severity", "notes",
]


def build_rows() -> list[dict]:
    rows: list[dict] = []
    idx = 0
    for bucket, items in BUCKETS:
        for stage, text, is_comp, crf, mdr, severity, notes in items:
            idx += 1
            rows.append(
                {
                    "id": f"m{idx:03d}",
                    "bucket": bucket,
                    "journey_stage": stage,
                    "order_ref": "",
                    "text": text,
                    "gold_is_complaint": str(is_comp).lower(),
                    "gold_clinical_red_flag": str(crf).lower(),
                    "gold_potential_mdr": str(mdr).lower(),
                    "gold_severity": severity,
                    "notes": notes,
                }
            )
    return rows


def main() -> None:
    rows = build_rows()
    out = Path(__file__).resolve().parent / "dataset.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    print(f"Wrote {len(rows)} messages to {out}")
    for b, n in counts.items():
        print(f"  {b}: {n}")


if __name__ == "__main__":
    main()
