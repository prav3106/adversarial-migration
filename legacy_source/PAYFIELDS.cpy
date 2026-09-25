      *> PAYFIELDS.cpy — shared pay result fields
      *> Included by TAXCALC, DEDUCT, PAYSLIP.
       01  PAY-RESULTS.
           05  PF-GROSS-PAY      PIC 9(7)V9(2).
           05  PF-TAX-AMOUNT     PIC 9(7)V9(2).
           05  PF-DEDUCTIONS     PIC 9(5)V9(2).
           05  PF-NET-PAY        PIC S9(7)V9(2).
