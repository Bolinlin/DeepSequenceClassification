# coding: utf-8
import logging
logger = logging.getLogger("DeepSequenceClassification_Model")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)s %(levelname)s %(asctime)s:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.info("Started Logger")

import theano, keras
logger.info("Using Keras version %s" % keras.__version__)
logger.info("Using Theano version %s" % theano.__version__)
from keras.models import Sequential, Graph
from keras.layers.core import Dense, Dropout, Activation, TimeDistributedDense, Flatten, Merge, Permute, Reshape, TimeDistributedMerge
from keras.layers.embeddings import Embedding
from keras.layers.recurrent import LSTM, GRU
from keras.layers.convolutional import Convolution1D, MaxPooling1D, Convolution2D, MaxPooling2D
from keras.preprocessing.sequence import pad_sequences
from keras.utils.np_utils import accuracy

import numpy as np
import glob
import json
import time
import os, sys


import preprocess as pp
import vector_utils as vtu
def vectorize_data(filenames, maxlen=100, max_charlen=20, output_label_size=6, output_label_dict=None, output_type="boundary", return_chars=False):
    assert output_label_dict is not None, "The output label dictionary should be specified before vectorizing data"
    X = []
    X_char = []
    Y = []
    for i, filename in enumerate(filenames):
        for docid, doc in pp.get_documents(filename):
            for seq in pp.get_sequences(doc):
                x = []
                x_char = []
                y = []
                for token in seq:
                    x.append(1 + token.word_index) # Add 1 to include token for padding
                    if return_chars:
                        x_char.append((1 + np.array(token.char_seq)).tolist()) # Add 1 to include token for padding
                    if output_type == "category":
                        y_idx = 1 + output_label_dict.get(token.c_label, -1) # Add 1 to include token for padding
                    else:
                        y_idx = 1 + output_label_dict.get(token.b_label, -1) # Add 1 to include token for padding
                    y.append(y_idx) # Add 1 to include token for padding
                X.append(x)
                if return_chars:
                    padded_sequence = pad_sequences([[] for k in xrange(maxlen - len(x_char))], maxlen=max_charlen).tolist() +\
                            pad_sequences(x_char[:maxlen], maxlen=max_charlen).tolist()
                    X_char.append(padded_sequence)
                Y.append(y)
    X = pad_sequences(X, maxlen=maxlen)
    Y = pad_sequences(Y, maxlen=maxlen)
    
    X = np.array(X)
    Y = vtu.to_onehot(Y, output_label_size)
    if return_chars:
        return X, Y, np.array(X_char)
    return X, Y

def gen_model(vocab_size=100, embedding_size=128, maxlen=100, output_size=6, hidden_layer_size=100, num_hidden_layers = 1, RNN_LAYER_TYPE="LSTM"):
    RNN_CLASS = LSTM
    if RNN_LAYER_TYPE == "GRU":
        RNN_CLASS = GRU
    logger.info("Parameters: vocab_size = %s, embedding_size = %s, maxlen = %s, output_size = %s, hidden_layer_size = %s, " %\
            (vocab_size, embedding_size, maxlen, output_size, hidden_layer_size))
    logger.info("Building Model")
    model = Sequential()
    logger.info("Init Model with vocab_size = %s, embedding_size = %s, maxlen = %s" % (vocab_size, embedding_size, maxlen))
    model.add(Embedding(vocab_size, embedding_size, input_length=maxlen))
    logger.info("Added Embedding Layer")
    model.add(Dropout(0.5))
    logger.info("Added Dropout Layer")
    for i in xrange(num_hidden_layers):
        model.add(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True))
        logger.info("Added %s Layer" % RNN_LAYER_TYPE)
        model.add(Dropout(0.5))
        logger.info("Added Dropout Layer")
    model.add(RNN_CLASS(output_dim=output_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True))
    logger.info("Added %s Layer" % RNN_LAYER_TYPE)
    model.add(Dropout(0.5))
    logger.info("Added Dropout Layer")
    model.add(TimeDistributedDense(output_size, activation="softmax"))
    logger.info("Added Dropout Layer")
    logger.info("Created model with following config:\n%s" % json.dumps(model.get_config(), indent=4))
    logger.info("Compiling model with optimizer %s" % optimizer)
    start_time = time.time()
    model.compile(loss='categorical_crossentropy', optimizer=optimizer)
    total_time = time.time() - start_time
    logger.info("Model compiled in %.4f seconds." % total_time)
    return model


def gen_model_brnn(vocab_size=100, embedding_size=128, maxlen=100, output_size=6, hidden_layer_size=100, num_hidden_layers = 1, RNN_LAYER_TYPE="LSTM"):
    RNN_CLASS = LSTM
    if RNN_LAYER_TYPE == "GRU":
        RNN_CLASS = GRU
    logger.info("Parameters: vocab_size = %s, embedding_size = %s, maxlen = %s, output_size = %s, hidden_layer_size = %s, " %\
            (vocab_size, embedding_size, maxlen, output_size, hidden_layer_size))
    logger.info("Building Graph model for Bidirectional RNN")
    model = Graph()
    model.add_input(name='input', input_shape=(maxlen,), dtype=int)
    logger.info("Added Input node")
    logger.info("Init Model with vocab_size = %s, embedding_size = %s, maxlen = %s" % (vocab_size, embedding_size, maxlen))
    model.add_node(Embedding(vocab_size, embedding_size, input_length=maxlen), name='embedding', input='input')
    logger.info("Added Embedding node")
    model.add_node(Dropout(0.5), name="dropout_0", input="embedding")
    logger.info("Added Dropout Node")
    for i in xrange(num_hidden_layers):
        last_dropout_name = "dropout_%s" % i
        forward_name, backward_name, dropout_name = ["%s_%s" % (k, i + 1) for k in ["forward", "backward", "dropout"]]
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True), name=forward_name, input=last_dropout_name)
        logger.info("Added %s forward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True, go_backwards=True), name=backward_name, input=last_dropout_name)
        logger.info("Added %s backward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(Dropout(0.5), name=dropout_name, inputs=[forward_name, backward_name])
        logger.info("Added Dropout node[%s]" % (i+1))
    model.add_node(TimeDistributedDense(output_size, activation="softmax"), name="tdd", input=dropout_name)
    logger.info("Added TimeDistributedDense node")
    model.add_output(name="output", input="tdd")
    logger.info("Added Output node")
    logger.info("Created model with following config:\n%s" % model.get_config())
    logger.info("Compiling model with optimizer %s" % optimizer)
    start_time = time.time()
    model.compile(optimizer, {"output": 'categorical_crossentropy'})
    total_time = time.time() - start_time
    logger.info("Model compiled in %.4f seconds." % total_time)
    return model


def gen_model_brnn_multitask(vocab_size=100, embedding_size=128, maxlen=100, output_size=[6, 96], hidden_layer_size=100, num_hidden_layers = 1, RNN_LAYER_TYPE="LSTM"):
    RNN_CLASS = LSTM
    if RNN_LAYER_TYPE == "GRU":
        RNN_CLASS = GRU
    logger.info("Parameters: vocab_size = %s, embedding_size = %s, maxlen = %s, output_size = %s, hidden_layer_size = %s, " %\
            (vocab_size, embedding_size, maxlen, output_size, hidden_layer_size))
    logger.info("Building Graph model for Bidirectional RNN")
    model = Graph()
    model.add_input(name='input', input_shape=(maxlen,), dtype=int)
    logger.info("Added Input node")
    logger.info("Init Model with vocab_size = %s, embedding_size = %s, maxlen = %s" % (vocab_size, embedding_size, maxlen))
    model.add_node(Embedding(vocab_size, embedding_size, input_length=maxlen, mask_zero=True), name='embedding', input='input')
    logger.info("Added Embedding node")
    model.add_node(Dropout(0.5), name="dropout_0", input="embedding")
    logger.info("Added Dropout Node")
    for i in xrange(num_hidden_layers):
        last_dropout_name = "dropout_%s" % i
        forward_name, backward_name, dropout_name = ["%s_%s" % (k, i + 1) for k in ["forward", "backward", "dropout"]]
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True), name=forward_name, input=last_dropout_name)
        logger.info("Added %s forward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True, go_backwards=True), name=backward_name, input=last_dropout_name)
        logger.info("Added %s backward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(Dropout(0.5), name=dropout_name, inputs=[forward_name, backward_name])
        logger.info("Added Dropout node[%s]" % (i+1))
    output_names = []
    for i, output_task_size in enumerate(output_size):
        tdd_name, output_name = "tdd_%s" % i, "output_%s" % i
        model.add_node(TimeDistributedDense(output_task_size, activation="softmax"), name=tdd_name, input=dropout_name)
        logger.info("Added TimeDistributedDense node %s with output_size")
        model.add_output(name=output_name, input=tdd_name)
        output_names.append(output_name)
    logger.info("Added Output node")
    logger.info("Created model with following config:\n%s" % model.get_config())
    logger.info("Compiling model with optimizer %s" % optimizer)
    start_time = time.time()
    model.compile(optimizer, {k: 'categorical_crossentropy' for k in output_names})
    total_time = time.time() - start_time
    logger.info("Model compiled in %.4f seconds." % total_time)
    return model, output_names


def gen_model_brnn_cnn_multitask(vocab_size=100, char_vocab_size = 100, embedding_size=128, char_embedding_size = 50, nb_filters = 10,\
        maxlen=100, max_charlen=20, output_size=[6, 96], hidden_layer_size=100, num_hidden_layers = 1, RNN_LAYER_TYPE="LSTM"):
    RNN_CLASS = LSTM
    if RNN_LAYER_TYPE == "GRU":
        RNN_CLASS = GRU
    logger.info("Parameters: vocab_size = %s, embedding_size = %s, maxlen = %s, output_size = %s, hidden_layer_size = %s, " %\
            (vocab_size, embedding_size, maxlen, output_size, hidden_layer_size))
    logger.info("CNN Parameters: char_vocab_size = %s, char_embedding_size = %s, max_charlen = %s, nb_filters = %s" %\
            (char_vocab_size, char_embedding_size, max_charlen, nb_filters))
    
    logger.info("Building sequential CNN model for char based word embeddings")
    model_cnn = Sequential()
    model_cnn.add(Embedding(char_vocab_size, char_embedding_size, input_length=maxlen*max_charlen))
    model_cnn.add(Reshape((maxlen, max_charlen, char_embedding_size)))
    model_cnn.add(Permute((3,1,2)))
    model_cnn.add(Convolution2D(nb_filters, 1, 2, border_mode='same'))
    model_cnn.add(Permute((2,1,3)))
    model_cnn.add(MaxPooling2D((2, 2)))
    model_cnn.add(Reshape((maxlen, 50)))

    logger.info("Building embedding model for word embeddings")
    model_word = Sequential()
    model_word.add(Embedding(vocab_size, embedding_size, input_length=maxlen))

    logger.info("Building Graph model for Bidirectional RNN")

    model = Graph()
    model.add_input(name='input1', input_shape=(maxlen,), dtype=int)
    logger.info("Added Input node 1")
    model.add_node(model_word, name="embed_word", input="input1")

    model.add_input(name='input2', input_shape=(maxlen*max_charlen,), dtype=int)
    logger.info("Added Input node 2")
    model.add_node(model_cnn, name="cnn_feature", input="input2")

    logger.info("Init Model with vocab_size = %s, embedding_size = %s, maxlen = %s" % (vocab_size, embedding_size, maxlen))
    model.add_node(Dropout(0.5), name="dropout_0", inputs=["embed_word", "cnn_feature"])
    logger.info("Added Dropout Node")
    for i in xrange(num_hidden_layers):
        last_dropout_name = "dropout_%s" % i
        forward_name, backward_name, dropout_name = ["%s_%s" % (k, i + 1) for k in ["forward", "backward", "dropout"]]
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True), name=forward_name, input=last_dropout_name)
        logger.info("Added %s forward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(RNN_CLASS(output_dim=hidden_layer_size, activation='sigmoid', inner_activation='hard_sigmoid', return_sequences=True, go_backwards=True), name=backward_name, input=last_dropout_name)
        logger.info("Added %s backward node[%s]" % (RNN_LAYER_TYPE, i+1))
        model.add_node(Dropout(0.5), name=dropout_name, inputs=[forward_name, backward_name])
        logger.info("Added Dropout node[%s]" % (i+1))
    output_names = []
    for i, output_task_size in enumerate(output_size):
        tdd_name, output_name = "tdd_%s" % i, "output_%s" % i
        model.add_node(TimeDistributedDense(output_task_size, activation="softmax"), name=tdd_name, input=dropout_name)
        logger.info("Added TimeDistributedDense node %s with output_size")
        model.add_output(name=output_name, input=tdd_name)
        output_names.append(output_name)
    logger.info("Added Output node")
    logger.info("Created model with following config:\n%s" % model.get_config())
    logger.info("Compiling model with optimizer %s" % optimizer)
    start_time = time.time()
    model.compile(optimizer, {k: 'categorical_crossentropy' for k in output_names})
    total_time = time.time() - start_time
    logger.info("Model compiled in %.4f seconds." % total_time)
    return model, output_names, (model_word, model_cnn)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to config file", default="config.json")
    parser.add_argument("--verbose", help="Verbosity level in training.", default=2, type=int)
    parser.add_argument("-w", "--weights", help="Path to weights file", default=None)
    parser.add_argument("-e", "--base_epochs", help="Resume training from number of epochs", default=0, type=int)
    args = parser.parse_args()
    config_file = args.config
    verbosity = args.verbose
    weights_file = args.weights
    base_epochs = args.base_epochs
    if weights_file is None and base_epochs != 0:
        logger.warn("base_epochs should only be set when loading weights. Continuing with base_epochs = 0")
    else:
        logger.info("Will load model weights from %s and train using base_epochs = %s" % (weights_file, base_epochs))
    logger.info("Using config file: %s and verbosity: %s" % (config_file, verbosity))

    CONFIG = json.load(open(config_file))

    BASE_DATA_DIR = CONFIG["BASE_DATA_DIR"]
    DATA_DIR = "%s/%s" % (BASE_DATA_DIR, CONFIG["DATA_DIR"])
    vocab_file = "%s/%s" % (BASE_DATA_DIR, CONFIG["vocab_file"])
    char_vocab_file = "%s/%s" % (BASE_DATA_DIR, CONFIG.get("char_vocab_file", None))
    labels_file = "%s/%s" % (BASE_DATA_DIR, CONFIG["labels_file"])
    boundary_file = "%s/%s" % (BASE_DATA_DIR, CONFIG["boundary_file"])
    category_file = "%s/%s" % (BASE_DATA_DIR, CONFIG["category_file"])
    BASE_OUT_DIR = CONFIG["BASE_OUT_DIR"]
    SAVE_MODEL_DIR = "%s/%s" % (BASE_OUT_DIR, CONFIG["SAVE_MODEL_DIR"])
    label_type = CONFIG.get("label_type", "boundary")
    MODEL_PREFIX = CONFIG.get("MODEL_PREFIX", "model")
    maxlen = CONFIG["maxlen"]
    max_charlen = CONFIG.get("max_charlen", 20)
    num_hidden_layers = CONFIG["num_hidden_layers"]
    embedding_size = CONFIG["embedding_size"]
    char_embedding_size = CONFIG.get("char_embedding_size", 100)
    nb_filters = CONFIG.get("nb_filters", 10)
    hidden_layer_size = CONFIG["hidden_layer_size"]
    RNN_LAYER_TYPE = CONFIG.get("RNN_LAYER_TYPE", "LSTM")
    optimizer = CONFIG["optimizer"]
    n_epochs = CONFIG["n_epochs"] + base_epochs
    save_every = CONFIG["save_every"]
    model_type = CONFIG.get("model_type", "rnn") # rnn, brnn

    RNN_CLASS = LSTM
    if RNN_LAYER_TYPE == "GRU":
        RNN_CLASS = GRU

    index_word, word_dict = pp.load_vocab(vocab_file)
    char_dict = {}
    if char_vocab_file is not None:
        index_char, char_dict = pp.load_vocab(char_vocab_file)
        char_vocab_size = len(index_char) + 2 # Add offset for OOV and padding
    pp.WordToken.set_vocab(word_dict = word_dict, char_dict = char_dict)
    index_labels, labels_dict = pp.load_vocab(labels_file)
    index_boundary, boundary_dict = pp.load_vocab(boundary_file)
    index_category, category_dict = pp.load_vocab(category_file)
    vocab_size = len(index_word) + pp.WordToken.VOCAB + 1 # Add offset of VOCAB and then extra token for padding
    labels_size = len(index_labels) + 1 # Add extra token for padding
    boundary_size = len(index_boundary) + 1 # Add extra token for padding 
    category_size = len(index_category) + 1 # Add extra token for padding

    logger.info("Parameters: vocab_size = %s, label_type = %s, labels_size = %s, embedding_size = %s, maxlen = %s, boundary_size = %s, category_size = %s, embedding_size = %s, hidden_layer_size = %s" %\
                    (vocab_size, label_type, labels_size, embedding_size, maxlen, boundary_size, category_size, embedding_size, hidden_layer_size))

    # Read the data
    if sum([os.path.isfile("%s/%s" % (BASE_DATA_DIR, k)) for k in CONFIG["data_vectors"]]) < len(CONFIG["data_vectors"]):
        logger.info("Preprocessed vectors don't exist. Generating again.")
        CV_filenames = [glob.glob("%s/%s/*.xml" % (DATA_DIR, i)) for i in range(1,6)]

        train_files = reduce(lambda x, y: x + y, CV_filenames[0:4])
        test_files = reduce(lambda x, y: x + y, CV_filenames[4:])
        if model_type == "brnn_cnn_multitask":
            assert char_vocab_file is not None, "In order to use char CNN one must set a char_vocab_file to the character vocab file in %s" % config_file
            Y_train = []
            Y_test = []
            X_train, Y_train_t = vectorize_data(train_files, maxlen=maxlen, output_label_size=boundary_size, output_label_dict=boundary_dict, output_type="boundary")
            X_test, Y_test_t = vectorize_data(test_files, maxlen=maxlen, output_label_size=boundary_size, output_label_dict=boundary_dict, output_type="boundary")
            Y_train.append(Y_train_t)
            Y_test.append(Y_test_t)
            X_train, Y_train_t, X_char_train = vectorize_data(train_files, maxlen=maxlen, max_charlen = max_charlen, output_label_size=category_size, output_label_dict=category_dict, output_type="category", return_chars=True) # Only get the chars the 2nd time to imporve computation
            X_test, Y_test_t, X_char_test = vectorize_data(test_files, maxlen=maxlen, max_charlen = max_charlen, output_label_size=category_size, output_label_dict=category_dict, output_type="category", return_chars=True)
            Y_train.append(np.array(Y_train_t))
            Y_test.append(np.array(Y_test_t))
            logger.info("Saving preprocessed vectors for faster computation next time in %s files." % ["%s/%s" % (BASE_DATA_DIR, k) for k in CONFIG["data_vectors"]])
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][0]), X_train)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][1]), X_char_train)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][2]), vtu.onehot_to_idxarr(Y_train[0]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][3]), vtu.onehot_to_idxarr(Y_train[1]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][4]), X_test)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][5]), X_char_test)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][6]), vtu.onehot_to_idxarr(Y_test[0]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][7]), vtu.onehot_to_idxarr(Y_test[1]))
            # Reshape arrays after saving
            X_char_train = X_char_train.reshape((X_char_train.shape[0], X_char_train.shape[1]*X_char_train.shape[2]))
            X_char_test = X_char_test.reshape((X_char_test.shape[0], X_char_test.shape[1]*X_char_test.shape[2]))
            logger.info("Loaded X_char_train: %s, X_char_test: %s" % (X_char_train.shape, X_char_test.shape))
        elif model_type == "brnn_multitask":
            Y_train = []
            Y_test = []
            X_train, Y_train_t = vectorize_data(train_files, maxlen=maxlen, output_label_size=boundary_size, output_label_dict=boundary_dict, output_type="boundary")
            X_test, Y_test_t = vectorize_data(test_files, maxlen=maxlen, output_label_size=boundary_size, output_label_dict=boundary_dict, output_type="boundary")
            Y_train.append(Y_train_t)
            Y_test.append(Y_test_t)
            X_train, Y_train_t = vectorize_data(train_files, maxlen=maxlen, output_label_size=category_size, output_label_dict=category_dict, output_type="category")
            X_test, Y_test_t = vectorize_data(test_files, maxlen=maxlen, output_label_size=category_size, output_label_dict=category_dict, output_type="category")
            Y_train.append(np.array(Y_train_t))
            Y_test.append(np.array(Y_test_t))
            logger.info("Saving preprocessed vectors for faster computation next time in %s files." % ["%s/%s" % (BASE_DATA_DIR, k) for k in CONFIG["data_vectors"]])
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][0]), X_train)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][1]), vtu.onehot_to_idxarr(Y_train[0]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][2]), vtu.onehot_to_idxarr(Y_train[1]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][3]), X_test)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][4]), vtu.onehot_to_idxarr(Y_test[0]))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][5]), vtu.onehot_to_idxarr(Y_test[1]))
        else:
            X_train, Y_train = vectorize_data(train_files, maxlen=maxlen, output_label_size=labels_size, output_label_dict=labels_dict, output_type=label_type)
            X_test, Y_test = vectorize_data(test_files, maxlen=maxlen, output_label_size=labels_size, output_label_dict=labels_dict, output_type=label_type)
            logger.info("Saving preprocessed vectors for faster computation next time in %s files." % ["%s/%s" % (BASE_DATA_DIR, k) for k in CONFIG["data_vectors"]])
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][0]), X_train)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][1]), vtu.onehot_to_idxarr(Y_train))
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][2]), X_test)
            np.save("%s/%s" % (BASE_DATA_DIR, CONFIG["data_vectors"][3]), vtu.onehot_to_idxarr(Y_test))
    else:
        logger.info("Preprocessed vectors exist. Loading from files %s." % ["%s/%s" % (BASE_DATA_DIR, k) for k in CONFIG["data_vectors"]])
        if model_type == "brnn_multitask":
            X_train, X_test = [np.load("%s/%s" % (BASE_DATA_DIR, k)) for k in CONFIG["data_vectors"][::3]]
            Y_train = [vtu.to_onehot(np.load("%s/%s" % (BASE_DATA_DIR, k[0])), k[1]) for k in zip(CONFIG["data_vectors"][1:3], [boundary_size, category_size])]
            Y_test = [vtu.to_onehot(np.load("%s/%s" % (BASE_DATA_DIR, k[0])), k[1]) for k in zip(CONFIG["data_vectors"][4:6], [boundary_size, category_size])]
        elif model_type == "brnn_cnn_multitask":
            X_train, X_test = [np.load("%s/%s" % (BASE_DATA_DIR, k)) for k in CONFIG["data_vectors"][::4]]
            X_char_train, X_char_test = [np.load("%s/%s" % (BASE_DATA_DIR, k)) for k in CONFIG["data_vectors"][1::4]]
            logger.info("Loaded X_char_train: %s, X_char_test: %s" % (X_char_train.shape, X_char_test.shape))
            X_char_train = X_char_train.reshape((X_char_train.shape[0], X_char_train.shape[1]*X_char_train.shape[2]))
            X_char_test = X_char_test.reshape((X_char_test.shape[0], X_char_test.shape[1]*X_char_test.shape[2]))
            Y_train = [vtu.to_onehot(np.load("%s/%s" % (BASE_DATA_DIR, k[0])), k[1]) for k in zip(CONFIG["data_vectors"][2:4], [boundary_size, category_size])]
            Y_test = [vtu.to_onehot(np.load("%s/%s" % (BASE_DATA_DIR, k[0])), k[1]) for k in zip(CONFIG["data_vectors"][6:8], [boundary_size, category_size])]
        else:
            X_train, X_test = [np.load("%s/%s" % (BASE_DATA_DIR, k)) for k in CONFIG["data_vectors"][::2]]
            Y_train, Y_test = [vtu.to_onehot(np.load("%s/%s" % (BASE_DATA_DIR, k)), labels_size) for k in CONFIG["data_vectors"][1::2]]
    if model_type == "brnn_multitask":
        logger.info("Loaded data shapes:\nX_train: %s, Y_train: %s\nX_test: %s, Y_test: %s" % (X_train.shape, [k.shape for k in Y_train], X_test.shape, [k.shape for k in Y_train]))
    elif model_type == "brnn_cnn_multitask":
        logger.info("Loaded data shapes:\nX_train: %s, X_char_train: %s, Y_train: %s\nX_test: %s, X_char_test: %s, Y_test: %s" % (X_train.shape, X_char_train.shape, [k.shape for k in Y_train], X_test.shape, X_char_test.shape, [k.shape for k in Y_train]))
    else:
        logger.info("Loaded data shapes:\nX_train: %s, Y_train: %s\nX_test: %s, Y_test: %s" % (X_train.shape, Y_train.shape, X_test.shape, Y_test.shape))
    
    if model_type == "brnn":
        model = gen_model_brnn(vocab_size=vocab_size, embedding_size=embedding_size, maxlen=maxlen, output_size=labels_size, hidden_layer_size=hidden_layer_size, num_hidden_layers = num_hidden_layers, RNN_LAYER_TYPE=RNN_LAYER_TYPE)
    elif model_type == "brnn_multitask":
        model, output_names = gen_model_brnn_multitask(vocab_size=vocab_size, embedding_size=embedding_size, maxlen=maxlen, output_size=[boundary_size, category_size], hidden_layer_size=hidden_layer_size, num_hidden_layers = num_hidden_layers, RNN_LAYER_TYPE=RNN_LAYER_TYPE)
    elif model_type == "brnn_cnn_multitask":
        model, output_names, _temp_models = gen_model_brnn_cnn_multitask(vocab_size=vocab_size, char_vocab_size = char_vocab_size, embedding_size=embedding_size, char_embedding_size = char_embedding_size, nb_filters = nb_filters, maxlen=maxlen, max_charlen=max_charlen, output_size=[boundary_size, category_size], hidden_layer_size=hidden_layer_size, num_hidden_layers = num_hidden_layers, RNN_LAYER_TYPE=RNN_LAYER_TYPE)
        logger.error("Feature under development.")
    else:
        model = gen_model(vocab_size=vocab_size, embedding_size=embedding_size, maxlen=maxlen, output_size=labels_size, hidden_layer_size=hidden_layer_size, num_hidden_layers = num_hidden_layers, RNN_LAYER_TYPE=RNN_LAYER_TYPE)

    if weights_file is not None:
        logger.info("Loading model weights from %s. Will continue training model from %s epochs." % (weights_file, base_epochs))
        model.load_weights(weights_file)
    for epoch in xrange(base_epochs, n_epochs, save_every):
        logger.info("Starting Epochs %s to %s" % (epoch, epoch + save_every))
        start_time = time.time()
        if model_type == "brnn":
            model.fit({"input": X_train,"output": Y_train}, validation_data={"input": X_test, "output": Y_test}, nb_epoch=save_every, verbose=verbosity)
            Y_out = model.predict({'input': X_test})['output']
            Y_idx = (Y_test[:,:,0] == 0) & (Y_test[:,:,5] == 0) # Get indexes of only those tokens which correspond to entitites
            # Calculate accuracy only based on correct entity identity
            acc = accuracy(np.argmax(np.array(Y_out), axis=-1)[Y_idx], np.argmax(Y_test, axis=-1)[Y_idx])
            logger.info("Output test accuracy: %.3f" % acc*100)
        elif model_type == "brnn_multitask":
            model.fit({"input": X_train, output_names[0]: Y_train[0], output_names[1]: Y_train[1]},\
                    validation_data={"input": X_test, output_names[0]: Y_test[0], output_names[1]: Y_test[1]}, nb_epoch=save_every, verbose=verbosity)
            Y_out = model.predict({'input': X_test})
            Y_idx = (Y_test[0][:,:,0] == 0) & (Y_test[0][:,:,5] == 0) # Get indexes of only those tokens which correspond to entitites
            # Calculate accuracy only based on correct entity identity
            acc1 = accuracy(np.argmax(np.array(Y_out[output_names[0]]), axis=-1)[Y_idx], np.argmax(Y_test[0], axis=-1)[Y_idx])
            acc2 = accuracy(np.argmax(np.array(Y_out[output_names[1]]), axis=-1)[Y_idx], np.argmax(Y_test[1], axis=-1)[Y_idx])
            logger.info("Test accuracy: %.3f[%s], %.3f[%s]" % (acc1* 100, output_names[0], acc2 * 100, output_names[1]))
        elif model_type == "brnn_cnn_multitask":
            model.fit({"input1": X_train, "input2": X_char_train, output_names[0]: Y_train[0], output_names[1]: Y_train[1]},\
                    validation_data={"input1": X_test, "input2": X_char_test, output_names[0]: Y_test[0], output_names[1]: Y_test[1]}, nb_epoch=save_every, verbose=verbosity)
            Y_out = model.predict({'input1': X_test, "input2": X_char_test})
            Y_idx = (Y_test[0][:,:,0] == 0) & (Y_test[0][:,:,5] == 0) # Get indexes of only those tokens which correspond to entitites
            # Calculate accuracy only based on correct entity identity
            acc1 = accuracy(np.argmax(np.array(Y_out[output_names[0]]), axis=-1)[Y_idx], np.argmax(Y_test[0], axis=-1)[Y_idx])
            acc2 = accuracy(np.argmax(np.array(Y_out[output_names[1]]), axis=-1)[Y_idx], np.argmax(Y_test[1], axis=-1)[Y_idx])
            logger.info("Test accuracy: %.3f[%s], %.3f[%s]" % (acc1* 100, output_names[0], acc2 * 100, output_names[1]))
            logger.error("Feature under development.")
            #sys.exit(1)
        else:
            model.fit(X_train,Y_train, validation_data=(X_test, Y_test), nb_epoch=save_every, verbose=verbosity, show_accuracy=True)
        total_time = time.time() - start_time
        logger.info("Finished training %.3f epochs in %s seconds with %.5f seconds/epoch" % (save_every, total_time, total_time * 1.0/ save_every))
        model.save_weights("%s/%s_%s_h%s-%s.h5" % (SAVE_MODEL_DIR, MODEL_PREFIX, model_type, num_hidden_layers, epoch), overwrite=True)

