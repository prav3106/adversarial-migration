      *> ============================================================
      *> PAYSLIP.cbl — Final payslip assembly
      *>
      *> Input record (80 bytes, SEQUENTIAL):
      *>   PS-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   PS-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
      *>   PS-TAX-AMOUNT    PIC 9(7)V9(2)   offset 15  len  9
      *>   PS-DEDUCTIONS    PIC 9(5)V9(2)   offset 24  len  7
      *>   FILLER           PIC X(49)       offset 31  len 49
      *>
      *> Output record (80 bytes):
      *>   PS-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   PS-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
      *>   PS-TAX-AMOUNT    PIC 9(7)V9(2)   offset 15  len  9
      *>   PS-DEDUCTIONS    PIC 9(5)V9(2)   offset 24  len  7
      *>   PS-NET-PAY       PIC S9(7)V9(2)  offset 31  len  9  (signed DISPLAY)
      *>   PS-NET-UNSIGNED  PIC 9(7)V9(2)   offset 40  len  9  (unsigned copy)
      *>   FILLER           PIC X(31)       offset 49  len 31
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYSLIP.

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
           05  PS-EMP-ID         PIC 9(6).
           05  PS-GROSS-PAY      PIC 9(7)V9(2).
           05  PS-TAX-AMOUNT     PIC 9(7)V9(2).
           05  PS-DEDUCTIONS     PIC 9(5)V9(2).
           05  FILLER            PIC X(49).

       01  WS-OUTPUT-RECORD.
           05  PS-OUT-EMP-ID     PIC 9(6).
           05  PS-OUT-GROSS      PIC 9(7)V9(2).
           05  PS-OUT-TAX        PIC 9(7)V9(2).
           05  PS-OUT-DEDUCT     PIC 9(5)V9(2).
           05  PS-NET-PAY        PIC S9(7)V9(2).
           05  PS-NET-UNSIGNED   PIC 9(7)V9(2).
           05  FILLER            PIC X(31).

       01  WS-WORK.
           05  WS-NET-WORK       PIC S9(9)V9(4).
           05  WS-COMP3-STORE    PIC 9(7)V9(2) USAGE COMP-3.

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
               NOT AT END PERFORM CALC-PAYSLIP
           END-READ.

       CALC-PAYSLIP.
           MOVE PS-EMP-ID       TO PS-OUT-EMP-ID
      *> TRAP: WS-NET-WORK is signed; net pay can go negative when
      *>       deductions+tax exceed gross — PS-NET-PAY is signed so stores sign
           COMPUTE WS-NET-WORK =
               PS-GROSS-PAY - PS-TAX-AMOUNT - PS-DEDUCTIONS
           MOVE WS-NET-WORK     TO PS-NET-PAY
      *> Intermediate COMP-3 store and reload preserves implied decimal (V)
           MOVE PS-GROSS-PAY    TO WS-COMP3-STORE
           MOVE WS-COMP3-STORE  TO PS-OUT-GROSS
           MOVE PS-TAX-AMOUNT   TO PS-OUT-TAX
           MOVE PS-DEDUCTIONS   TO PS-OUT-DEDUCT
      *> TRAP: MOVE of signed PS-NET-PAY to unsigned PS-NET-UNSIGNED drops sign
      *>       absolute value stored, not clamped to zero
           MOVE PS-NET-PAY      TO PS-NET-UNSIGNED
           WRITE OF-RECORD FROM WS-OUTPUT-RECORD.
