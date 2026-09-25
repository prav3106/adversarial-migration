      *> ============================================================
      *> VALIDATE.cbl — Employee record validation
      *>
      *> Input record (80 bytes, SEQUENTIAL):
      *>   VL-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   VL-EMP-NAME      PIC X(20)       offset  6  len 20
      *>   VL-HOURS-WORKED  PIC S9(3)V9(2)  offset 26  len  5  (signed DISPLAY)
      *>   VL-HOURLY-RATE   PIC 9(4)V9(2)   offset 31  len  6
      *>   FILLER           PIC X(43)       offset 37  len 43
      *>
      *> Output record (80 bytes):
      *>   VL-EMP-ID        PIC 9(6)        offset  0  len  6
      *>   VL-EMP-NAME      PIC X(20)       offset  6  len 20
      *>   VL-HOURS-CLEAN   PIC 9(3)V9(2)   offset 26  len  5  (unsigned)
      *>   VL-HOURLY-CLEAN  PIC 9(4)V9(2)   offset 31  len  6
      *>   VL-VALID-FLAG    PIC X(1)        offset 37  len  1
      *>   FILLER           PIC X(42)       offset 38  len 42
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. VALIDATE.

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
           05  VL-EMP-ID         PIC 9(6).
           05  VL-EMP-NAME       PIC X(20).
           05  VL-HOURS-WORKED   PIC S9(3)V9(2).
           05  VL-HOURLY-RATE    PIC 9(4)V9(2).
           05  FILLER            PIC X(43).

       01  WS-OUTPUT-RECORD.
           05  VL-OUT-EMP-ID     PIC 9(6).
           05  VL-OUT-EMP-NAME   PIC X(20).
           05  VL-HOURS-CLEAN    PIC 9(3)V9(2).
           05  VL-HOURLY-CLEAN   PIC 9(4)V9(2).
           05  VL-VALID-FLAG     PIC X(1).
           05  FILLER            PIC X(42).

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
               NOT AT END PERFORM VALIDATE-RECORD
           END-READ.

       VALIDATE-RECORD.
           MOVE VL-EMP-ID        TO VL-OUT-EMP-ID
           MOVE VL-EMP-NAME      TO VL-OUT-EMP-NAME
      *> TRAP: MOVE of signed VL-HOURS-WORKED into unsigned VL-HOURS-CLEAN
      *>       drops the sign; negative hours become their absolute value
           MOVE VL-HOURS-WORKED  TO VL-HOURS-CLEAN
           MOVE VL-HOURLY-RATE   TO VL-HOURLY-CLEAN
           IF VL-HOURLY-RATE > ZEROS AND VL-HOURS-CLEAN > ZEROS
               MOVE 'Y' TO VL-VALID-FLAG
           ELSE
               MOVE 'N' TO VL-VALID-FLAG
           END-IF
           WRITE OF-RECORD FROM WS-OUTPUT-RECORD.
