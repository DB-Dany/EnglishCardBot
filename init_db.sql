CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE base_words (
    id SERIAL PRIMARY KEY,
    word VARCHAR(100) NOT NULL,
    translation VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_words (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    word VARCHAR(100) NOT NULL,
    translation VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, word)
);

INSERT INTO base_words (word, translation) VALUES
('привет', 'hello'),
('мир', 'world'),
('книга', 'book'),
('солнце', 'sun'),
('вода', 'water'),
('дом', 'house'),
('мама', 'mother'),
('папа', 'father'),
('друг', 'friend'),
('любовь', 'love');