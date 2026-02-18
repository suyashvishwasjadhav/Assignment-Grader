# Copyright (c) 2024-2025 Suyash Vishwas Jadhav. All rights reserved.
# Project: EduEval - AI-Powered Automated Grading System
# Developer & Architect: Suyash Vishwas Jadhav

from datetime import datetime
from extensions import db
# from sqlalchemy.dialects.postgresql import ARRAY

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='student')  # 'student' or 'admin'
    login_type = db.Column(db.String(20), default='standard')  # 'standard' or 'google'
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    theme = db.Column(db.String(20), default='light')  # 'light' or 'dark'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    organization = db.relationship('Organization', back_populates='users')
    teacher = db.relationship('Teacher', back_populates='user', uselist=False)
    sent_messages = db.relationship('ChatMessage', foreign_keys='ChatMessage.sender_id', back_populates='sender')
    received_messages = db.relationship('ChatMessage', foreign_keys='ChatMessage.receiver_id', back_populates='receiver')
    submissions = db.relationship('Submission', back_populates='user')

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    users = db.relationship('User', back_populates='organization')

class Teacher(db.Model):
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True)
    subject = db.Column(db.String(100))
    
    # Relationships
    user = db.relationship('User', back_populates='teacher')
    assignments = db.relationship('Assignment', back_populates='creator')

class Assignment(db.Model):
    __tablename__ = 'assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=True)
    show_scores = db.Column(db.Boolean, default=False)  # Enable/disable student viewing of scores
    
    # Relationships
    creator = db.relationship('Teacher', back_populates='assignments')
    questions = db.relationship('Question', back_populates='assignment', cascade='all, delete-orphan')
    submissions = db.relationship('Submission', back_populates='assignment', cascade='all, delete-orphan')

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    answer_key = db.Column(db.Text)
    evaluation_method = db.Column(db.String(20), nullable=False)  # 'gemini' or 'answer_key'
    max_marks = db.Column(db.Integer, nullable=False)
    word_count = db.Column(db.Integer, nullable=False)
    
    # Relationships
    assignment = db.relationship('Assignment', back_populates='questions')
    responses = db.relationship('QuestionResponse', back_populates='question', cascade='all, delete-orphan')

class Submission(db.Model):
    __tablename__ = 'submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_marks = db.Column(db.Float)
    feedback = db.Column(db.Text)
    avg_relevance = db.Column(db.Float)
    avg_size_score = db.Column(db.Float)
    avg_grammar_score = db.Column(db.Float)
    
    # Relationships
    assignment = db.relationship('Assignment', back_populates='submissions')
    user = db.relationship('User', back_populates='submissions')
    responses = db.relationship('QuestionResponse', back_populates='submission', cascade='all, delete-orphan')

class QuestionResponse(db.Model):
    __tablename__ = 'question_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    extracted_text = db.Column(db.Text)
    first_five_words = db.Column(db.String(100))
    relevance_score = db.Column(db.Float)
    marks_awarded = db.Column(db.Float)
    feedback = db.Column(db.Text)
    image_paths = db.Column(db.JSON)
    size_score = db.Column(db.Float)
    grammar_score = db.Column(db.Float)
    word_count_actual = db.Column(db.Integer)
    possible_plagiarism = db.Column(db.Boolean, default=False)
    plagiarism_note = db.Column(db.Text)
    
    # Relationships
    submission = db.relationship('Submission', back_populates='responses')
    question = db.relationship('Question', back_populates='responses')

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], back_populates='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], back_populates='received_messages')
