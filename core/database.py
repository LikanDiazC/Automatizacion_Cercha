from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Usamos SQLite localmente para prototipar rápido
SQLALCHEMY_DATABASE_URL = "sqlite:///./mrp_muebles.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declaramos Base aquí para que todos los módulos lo compartan y evitar errores
Base = declarative_base()

# Función para obtener la conexión a la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()