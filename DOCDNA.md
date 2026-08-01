docdna  solo-utility  ·  overlays: agent-skill-package  ·  30840 lines JavaScript/Python/+2  ·  1 author  ·  MIT  ·  1 tag  ·  CI only

Documentation  4 of 34        Drift  1 of your 9 documents contradicts the code

WRONG NOW
  README.md             says `11 endpoints`; 29 routes detected

MISSING AND LOAD-BEARING  (29, showing 3)
  assure.data-classification Personal data sits on an entity this code treats as a person, and how long ...
  assure.threat-model   Personal data sits on an entity this code treats as a person, and how long ...
  assure.vdp            Anyone can use this, and anyone includes the person who finds the ...

NOT APPLICABLE  12 documents. No external body audits, certifies, or authorizes this before it
                ships, and no compliance workspace exists in the repository. Full ledger:
                .docdna/manifest.json
                assure.control-mapping is one signal away: q3_authorizer or sec.compliance_program

ASSUMED         assumed q2_operator=not-deployed, q3_authorizer=none, q4_decides_about_people=no.
                If a separate ops team runs this, up to 11 documents become required.

NOTE            I only see documentation committed to this repo. If your docs live in Confluence or
                Notion, say so and I will mark those rows present-elsewhere rather than missing.

NEXT            write 7 derivable documents  ·  refresh 1 drifted document  ·  --answer q2_operator
