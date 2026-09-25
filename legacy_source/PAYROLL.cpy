      *> PAYROLL.cpy — copybook for PAYROLL.cbl field layout
       01  PAYROLL-INPUT.
           05  PI-EMP-ID         PIC 9(6).
           05  PI-HOURS-WORKED   PIC 9(3)V9(2).
           05  PI-HOURLY-RATE    PIC 9(4)V9(2).
           05  PI-TAX-RATE       PIC 9(2)V9(4).
           05  FILLER            PIC X(57).

       01  PAYROLL-OUTPUT.
           05  PO-EMP-ID         PIC 9(6).
           05  PO-GROSS-PAY      PIC 9(7)V9(2).
           05  PO-TAX-AMOUNT     PIC 9(7)V9(2).
           05  PO-NET-PAY        PIC 9(7)V9(2).
           05  FILLER            PIC X(47).
