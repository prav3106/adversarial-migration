      *> ============================================================
      *> PAYROLL.cbl — sample COBOL module for migration demo
      *>
      *> Reads a fixed-width 80-byte employee payroll record and
      *> computes gross pay, tax withholding, and net pay.
      *>
      *> Input record layout (see PAYROLL.cpy):
      *>   EMP-ID       PIC 9(6)         offset  0  len 6
      *>   HOURS-WORKED PIC 9(3)V9(2)    offset  6  len 5   (e.g. 04000 = 40.00)
      *>   HOURLY-RATE  PIC 9(4)V9(2)    offset 11  len 6   (e.g. 025000 = 25.00 -> $250.00 ... wait 9(4)V9(2) = 6 chars: 4+2)
      *>   TAX-RATE     PIC 9(2)V9(4)    offset 17  len 6
      *>   FILLER       PIC X(63)        offset 23  len 57 (pad to 80)
      *>
      *> Output record layout (80 bytes):
      *>   EMP-ID       PIC 9(6)         offset  0  len 6
      *>   GROSS-PAY    PIC 9(7)V9(2)    offset  6  len 9
      *>   TAX-AMOUNT   PIC 9(7)V9(2)    offset 15  len 9
      *>   NET-PAY      PIC 9(7)V9(2)    offset 24  len 9
      *>   FILLER       PIC X(47)        offset 33  len 47
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-INPUT-RECORD.
           05  WS-EMP-ID         PIC 9(6).
           05  WS-HOURS-WORKED   PIC 9(3)V9(2).
           05  WS-HOURLY-RATE    PIC 9(4)V9(2).
           05  WS-TAX-RATE       PIC 9(2)V9(4).
           05  FILLER            PIC X(57).

       01  WS-OUTPUT-RECORD.
           05  WS-OUT-EMP-ID     PIC 9(6).
           05  WS-GROSS-PAY      PIC 9(7)V9(2).
           05  WS-TAX-AMOUNT     PIC 9(7)V9(2).
           05  WS-NET-PAY        PIC 9(7)V9(2).
           05  FILLER            PIC X(47).

       01  WS-WORK-AREA.
           05  WS-GROSS-WORK     PIC 9(9)V9(4).
           05  WS-TAX-WORK       PIC 9(9)V9(4).

       LINKAGE SECTION.
       01  L-INPUT-RECORD        PIC X(80).
       01  L-OUTPUT-RECORD       PIC X(80).

       PROCEDURE DIVISION USING L-INPUT-RECORD L-OUTPUT-RECORD.

       MAIN-PARA.
           MOVE L-INPUT-RECORD   TO WS-INPUT-RECORD

           COMPUTE WS-GROSS-WORK =
               WS-HOURS-WORKED * WS-HOURLY-RATE

           COMPUTE WS-TAX-WORK =
               WS-GROSS-WORK * WS-TAX-RATE

           MOVE WS-EMP-ID        TO WS-OUT-EMP-ID
           MOVE WS-GROSS-WORK    TO WS-GROSS-PAY
           MOVE WS-TAX-WORK      TO WS-TAX-AMOUNT

           COMPUTE WS-NET-PAY =
               WS-GROSS-PAY - WS-TAX-AMOUNT

           MOVE WS-OUTPUT-RECORD TO L-OUTPUT-RECORD

           STOP RUN.
