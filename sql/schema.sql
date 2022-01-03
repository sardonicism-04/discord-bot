-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (C) 2022 sardonicism-04
CREATE TABLE profiles (
    user_id            BIGINT PRIMARY KEY,
    created_at         TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
    hl_blocks          BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    receive_highlights BOOLEAN DEFAULT TRUE,
    timezone           TEXT DEFAULT NULL,
    hl_timeout         BIGINT CHECK (hl_timeout >= 1 AND hl_timeout <= 5) DEFAULT 1
);

CREATE TABLE guild_configs (
    guild_id          BIGINT PRIMARY KEY,
    prefix            TEXT DEFAULT 'n!',
    starboard         BOOLEAN DEFAULT FALSE,
    disabled_channels BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    disabled_commands TEXT[] DEFAULT ARRAY[]::TEXT[]
);

CREATE TABLE highlights (
    user_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (user_id, content),
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);

CREATE TABLE todos (
    user_id    BIGINT NOT NULL,
    content    TEXT NOT NULL,
    guild_id   TEXT NOT NULL, -- This can be an ID or @me, so we have to be inclusive
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    edited     BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);

-- Use foreign keys so that, if a config is deleted from the guild_configs
-- table, all related entries in starboard tables are also deleted
CREATE TABLE starboards (
    guild_id    BIGINT PRIMARY KEY,
    channel     BIGINT,
    threshold   BIGINT DEFAULT 5,
    format      VARCHAR(200) DEFAULT '⭐ **{stars}**',
    max_days    BIGINT CHECK (max_days > 1) DEFAULT 7,
    emoji       TEXT DEFAULT '⭐',
    ignored     BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    FOREIGN KEY (guild_id) REFERENCES guild_configs (guild_id) ON DELETE CASCADE
);

-- Same as above with foreign keys
CREATE TABLE stars (
    guild_id             BIGINT NOT NULL,
    message_id           BIGINT NOT NULL,
    channel_id           BIGINT NOT NULL,
    stars                BIGINT NOT NULL,
    starboard_message_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, message_id, channel_id),
    FOREIGN KEY (guild_id) REFERENCES starboards (guild_id) ON DELETE CASCADE
);

CREATE TABLE reminders (
    user_id    BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    content    VARCHAR(1000) NOT NULL,
    end_time   TIMESTAMP WITH TIME ZONE NOT NULL,
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);