from sqlalchemy import Column, Date, Integer, String

from .db import Base


class Patient(Base):
    __tablename__ = "patient"

    id = Column(Integer, primary_key=True)
    medical_record_number = Column(String(64), unique=True, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    email = Column(String(255))


class Encounter(Base):
    __tablename__ = "encounter"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    icd10_code = Column(String(8))
    diagnosis_note = Column(String(2048))
