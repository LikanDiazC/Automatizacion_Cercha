import json
import logging
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Cargar tu dataset que acabamos de crear
dataset_path = "datasets/triplets_acelerados.jsonl"
logger.info(f"Cargando datos desde {dataset_path}...")

train_examples = []
with open(dataset_path, "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        # TripletLoss requiere: [Anchor, Positivo, Negativo]
        train_examples.append(
            InputExample(texts=[data["anchor"], data["positive"], data["negative"]])
        )

logger.info(f"Se cargaron {len(train_examples)} triplets para entrenamiento.")

# 2. Cargar el modelo base open-source (Gratis y rápido)
model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
logger.info(f"Descargando modelo base: {model_name}...")
model = SentenceTransformer(model_name)

# 3. Preparar el DataLoader y la Función de Pérdida (Loss)
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.TripletLoss(model=model)

# 4. Iniciar el Entrenamiento (Fine-Tuning)
logger.info("Iniciando entrenamiento... (Esto puede tomar unos minutos dependiendo de tu PC)")
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=4, # 4 pasadas completas sobre los datos
    warmup_steps=100,
    show_progress_bar=True
)

# 5. Guardar tu nueva Inteligencia Artificial propia
output_path = "models/cercha-embedding-v1"
model.save(output_path)
logger.info(f"¡Éxito! Tu modelo experto en ferretería se ha guardado en: {output_path}")