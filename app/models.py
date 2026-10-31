from sqlalchemy import Column,Integer,String,Float,DateTime,ForeignKey,Text
from sqlalchemy.orm import relationship
from datetime import datetime,timezone
from .database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True); email=Column(String,unique=True,index=True); name=Column(String); password_hash=Column(String,default='mock')
class Report(Base):
 __tablename__='reports'
 id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id')); name=Column(String); created_at=Column(DateTime,default=lambda:datetime.now(timezone.utc)); status=Column(String,default='processing'); min_price=Column(Integer,default=300000); min_demand=Column(Integer,default=70); error_text=Column(Text,default='')
 cars=relationship('Car',cascade='all,delete-orphan',back_populates='report')
class Car(Base):
 __tablename__='cars'
 id=Column(Integer,primary_key=True); report_id=Column(Integer,ForeignKey('reports.id')); source_doc=Column(String); doc_number=Column(String); doc_date=Column(String); doc_type=Column(String,default='ban'); debtor_name=Column(String); inn=Column(String); debt_amount=Column(Float); vin=Column(String); make=Column(String); model=Column(String); year=Column(String); plate=Column(String); price=Column(Float); demand=Column(Integer); status=Column(String); vin_source=Column(String); vin_checked_at=Column(String); vin_error=Column(String,default=''); market_status=Column(String,default='not_configured'); market_checked_at=Column(String); demand_sources=Column(Text,default='[]'); link=Column(String); motivation_index=Column(Float); vzyskatel=Column(String); ip_id=Column(String); confidence=Column(Float,default=.6); market_sources=Column(Text,default='[]'); market_error=Column(Text,default=''); created_at=Column(DateTime,default=lambda:datetime.now(timezone.utc))
 report=relationship('Report',back_populates='cars')
