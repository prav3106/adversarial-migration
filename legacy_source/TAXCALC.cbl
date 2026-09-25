      *> ============================================================
      *> TAXCALC.cbl — Federal income tax calculation
      *>
      *> Input record (80 bytes, SEQUENTIAL):
      *>   TC-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   TC-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
      *>   TC-TAX-RATE      PIC 9(2)V9(4)   offset 15  len  6
      *>   FILLER           PIC X(59)       offset 21  len 59
      *>
      *> Output record (80 bytes):
      *>   TC-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   TC-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
      *>   TC-TAX-AMOUNT    PIC 9(7)V9(2)   offset 15  len  9
      *>   TC-BRACKET-TAX   PIC 9(7)V9(2)   offset 24  len  9
      *>   FILLER           PIC X(47)       offset 33  len 47
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TAXCALC.

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
           05  TC-EMP-ID         PIC 9(6).
           05  TC-GROSS-PAY      PIC 9(7)V9(2).
           05  TC-TAX-RATE       PIC 9(2)V9(4).
           05  FILLER            PIC X(59).

       01  WS-OUTPUT-RECORD.
           05  TC-OUT-EMP-ID     PIC 9(6).
           05  TC-OUT-GROSS-PAY  PIC 9(7)V9(2).
           05  TC-TAX-AMOUNT     PIC 9(7)V9(2).
           05  TC-BRACKET-TAX    PIC 9(7)V9(2).
           05  FILLER            PIC X(47).

       01  WS-WORK.
           05  WS-TAX-WORK       PIC 9(9)V9(4).
           05  WS-BRACKET-WORK   PIC 9(9)V9(4).

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
               NOT AT END PERFORM CALC-TAX
           END-READ.

       CALC-TAX.
           MOVE TC-EMP-ID      TO TC-OUT-EMP-ID
           MOVE TC-GROSS-PAY   TO TC-OUT-GROSS-PAY
      *> TRAP: COMPUTE ROUNDED uses ROUND_HALF_UP (not truncation)
      *>       TC-TAX-RATE has 4 decimal places so half-cent rounding fires frequently
           COMPUTE TC-TAX-AMOUNT ROUNDED =
               TC-GROSS-PAY * TC-TAX-RATE
      *> TRAP: bracketed tax via COMPUTE without ROUNDED — truncation only
      *>       bracket rate hardcoded 0.0275; result truncated not rounded
           COMPUTE WS-BRACKET-WORK =
               TC-GROSS-PAY * 0.0275
           MOVE WS-BRACKET-WORK TO TC-BRACKET-TAX
           WRITE OF-RECORD FROM WS-OUTPUT-RECORD.
