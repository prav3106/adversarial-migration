      *> ============================================================
      *> GROSSPAY.cbl — Gross pay calculation with overtime
      *>
      *> Input record (80 bytes, SEQUENTIAL):
      *>   GP-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   GP-HOURS-WORKED  PIC 9(3)V9(2)   offset  6  len  5
      *>   GP-HOURLY-RATE   PIC 9(4)V9(2)   offset 11  len  6
      *>   FILLER           PIC X(63)       offset 17  len 63
      *>
      *> Output record (80 bytes):
      *>   GP-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   GP-REGULAR-PAY   COMP-3 9(7)V9(2) offset  6  len  5
      *>   GP-OVERTIME-PAY  COMP-3 9(7)V9(2) offset 11  len  5
      *>   GP-GROSS-PAY     COMP-3 9(7)V9(2) offset 16  len  5
      *>   FILLER           PIC X(59)       offset 21  len 59
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GROSSPAY.

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
           05  GP-EMP-ID         PIC 9(6).
           05  GP-HOURS-WORKED   PIC 9(3)V9(2).
           05  GP-HOURLY-RATE    PIC 9(4)V9(2).
           05  FILLER            PIC X(63).

       01  WS-OUTPUT-RECORD.
           05  GP-OUT-EMP-ID     PIC 9(6).
           05  GP-REGULAR-PAY    PIC 9(7)V9(2) USAGE COMP-3.
           05  GP-OVERTIME-PAY   PIC 9(7)V9(2) USAGE COMP-3.
           05  GP-GROSS-PAY      PIC 9(7)V9(2) USAGE COMP-3.
           05  FILLER            PIC X(59).

       01  WS-WORK.
           05  WS-REG-HOURS      PIC 9(3)V9(2).
           05  WS-OT-HOURS       PIC 9(3)V9(2).
           05  WS-OT-RATE        PIC 9(4)V9(2).
           05  WS-WORK-PAY       PIC 9(9)V9(4).

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
               NOT AT END PERFORM CALC-GROSSPAY
           END-READ.

       CALC-GROSSPAY.
           MOVE GP-EMP-ID TO GP-OUT-EMP-ID
      *> Regular hours capped at 40.00
           IF GP-HOURS-WORKED > 40.00
               MOVE 40.00 TO WS-REG-HOURS
               SUBTRACT 40.00 FROM GP-HOURS-WORKED
                   GIVING WS-OT-HOURS
           ELSE
               MOVE GP-HOURS-WORKED TO WS-REG-HOURS
               MOVE ZEROS TO WS-OT-HOURS
           END-IF
      *> TRAP: COMPUTE without ROUNDED — fractional cents truncated toward zero
      *>       e.g. 40.00 * 12.555 = 502.20 not 502.21
           COMPUTE WS-WORK-PAY =
               WS-REG-HOURS * GP-HOURLY-RATE
           MOVE WS-WORK-PAY TO GP-REGULAR-PAY
      *> Overtime at 1.5x rate — COMPUTE truncates (no ROUNDED)
           COMPUTE WS-OT-RATE = GP-HOURLY-RATE * 1.5
      *> TRAP: overtime COMPUTE can overflow GP-OVERTIME-PAY at field max
      *>       9(7)V9(2) max = 9999999.99; WS-OT-HOURS * WS-OT-RATE may exceed it
           COMPUTE GP-OVERTIME-PAY =
               WS-OT-HOURS * WS-OT-RATE
           COMPUTE GP-GROSS-PAY =
               GP-REGULAR-PAY + GP-OVERTIME-PAY
           WRITE OF-RECORD FROM WS-OUTPUT-RECORD.
