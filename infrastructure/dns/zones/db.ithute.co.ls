$TTL 300
@   IN  SOA ns1.ithute.co.ls. hostmaster.ithute.co.ls. (
        2026091201 ; serial
        3600       ; refresh
        900        ; retry
        1209600    ; expire
        300        ; negative cache TTL
)

; The .ls parent must delegate ithute.co.ls to both names below and publish
; glue A records for them because the nameservers live inside this zone.
@           IN  NS      ns1.ithute.co.ls.
@           IN  NS      ns2.ithute.co.ls.
ns1         IN  A       204.12.205.224
ns2         IN  A       204.12.205.224

; Ithute-owned public services.
@           IN  A       204.12.205.224
www         IN  A       204.12.205.224
auth        IN  A       204.12.205.224
push        IN  A       204.12.205.224
realtime    IN  A       204.12.205.224
mail        IN  A       204.12.205.224
smtp        IN  CNAME   mail.ithute.co.ls.
imap        IN  CNAME   mail.ithute.co.ls.

; Mail and certificate policy for the Ithute domain.
@           IN  MX  10  mail.ithute.co.ls.
@           IN  TXT     "v=spf1 mx a ip4:204.12.205.224 -all"
_dmarc      IN  TXT     "v=DMARC1; p=quarantine; rua=mailto:postmaster@ithute.co.ls; adkim=s; aspf=s"
@           IN  CAA 0   issue "letsencrypt.org"
