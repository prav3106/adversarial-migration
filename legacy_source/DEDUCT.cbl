      *> ============================================================
      *> DEDUCT.cbl — Payroll deductions (health, retirement)
      *>
      *> Input record (80 bytes, SEQUENTIAL):
      *>   DD-EMP-ID           PIC 9(6)        offset  0  len  6
      *>   DD-GROSS-PAY        PIC 9(7)V9(2)   offset  6  len  9
      *>   DD-HEALTH-RATE      PIC 9(2)V9(4)   offset 15  len  6
      *>   DD-RETIREMENT-RATE  PIC 9(2)V9(4)   offset 21  len  6
      *>   FILLER              PIC X(53)       offset 27  len 53
      *>
      *> Output record (80 bytes):
      *>   DD-EMP-ID           PIC 9(6)        offset  0  len  6
      *>   DD-HEALTH-DED       PIC 9(5)V9(2)   offset  6  len  7
      *>   DD-RETIRE-DED       PIC 9(5)V9(2)   offset 13  len  7
      *>   DD-TOTAL-DEDUCT     PIC 9(5)V9(2)   offset 20  len  7
      *>   DD-AFTER-DEDUCT     PIC 9(7)V9(2)   offset 27  len  9
      *>   FILLER              PIC X(44)       offset 36  len 44
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEDUCT.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT INPUT-FILE  ASSIGN TO DYNAMIC WS-INPUT-PATH
               ORGANIZATION IS SEQUENTIAL.
           SELECT OUTPUT-FILE ASSIGN TO DYNAMIC WS-OUTPUT-PATH
               ORGANIZATION IS SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD  INPUT-FILE
           RECORD 80.
       01  IF-RECORD         PIC X(80).

       FD  OUTPUT-FILE
           RECORD 80.
       01  OF-RECORD         PIC X(80).

       WORKING-STORAGE SECTION.
       01  WS-INPUT-PATH     PIC X(256).
       01  WS-OUTPUT-PATH    PIC X(256).
       01  WS-EOF-FLAG       PIC X(1) VALUE 'N'.
       01  WS-ARGC           PIC 99.

       01  WS-INPUT-RECORD.
           05  DD-EMP-ID           PIC 9(6).
           05  DD-GROSS-PAY        PIC 9(7)V9(2).
           05  DD-HEALTH-RATE      PIC 9(2)V9(4).
           05  DD-RETIREMENT-RATE  PIC 9(2)V9(4).
           05  FILLER              PIC X(53).

       01  WS-OUTPUT-RECORD.
           05  DD-OUT-EMP-ID       PIC 9(6).
           05  DD-HEALTH-DED       PIC 9(5)V9(2).
           05  DD-RETIRE-DED       PIC 9(5)V9(2).
           05  DD-TOTAL-DEDUCT     PIC 9(5)V9(2).
           05  DD-AFTER-DEDUCT     PIC 9(7)V9(2).
           05  FILLER              PIC X(44).

       01  WS-WORK.
           05  WS-HEALTH-WORK      PIC 9(9)V9(4).
           05  WS-RETIRE-WORK      PIC 9(9)V9(4).

       PROCEDURE DIVISION.

       MAIN-PARA.
           MOVE 1 TO WS-ARGC
           ACCEPT WS-INPUT-PATH  FROM ARGUMENT-VALUE
           MOVE 2 TO WS-ARGC
           ACCEPT WS-OUTPUT-PATH FROM ARGUMENT-VALUE
           OPEN INPUT  INPUT-FILE
           OPEN OUTPUT OUTPUT-FILE
           PERFORM PROCESS-RECORDS UNTIL WS-EOF-FLAG = 'Y'
           CLOSE INPUT-FILE
           CLOSE OUTPUT-FILE
           STOP RUN.

       PROCESS-RECORDS.
           READ INPUT-FILE INTO WS-INPUT-RECORD
               AT END MOVE 'Y' TO WS-EOF-FLAG
               NOT AT END PERFORM CALC-DEDUCT
           END-READ.

       CALC-DEDUCT.
           MOVE DD-EMP-ID TO DD-OUT-EMP-ID
      *> TRAP: COMPUTE ROUNDED used for health — rounds half-up
           COMPUTE DD-HEALTH-DED ROUNDED =
               DD-GROSS-PAY * DD-HEALTH-RATE
      *> TRAP: mixed ROUNDED/non-ROUNDED sequence in same paragraph
      *>       retirement uses plain COMPUTE (truncates) immediately after ROUNDED
           COMPUTE WS-RETIRE-WORK =
               DD-GROSS-PAY * DD-RETIREMENT-RATE
           MOVE WS-RETIRE-WORK TO DD-RETIRE-DED
      *> TRAP: DD-TOTAL-DEDUCT is PIC 9(5)V9(2) max 99999.99
      *>       overflow silently drops high-order digits (high-order truncation)
           COMPUTE DD-TOTAL-DEDUCT =
               DD-HEALTH-DED + DD-RETIRE-DED
           COMPUTE DD-AFTER-DEDUCT =
               DD-GROSS-PAY - DD-TOTAL-DEDUCT
           WRITE OF-RECORD FROM WS-OUTPUT-RECORD.
