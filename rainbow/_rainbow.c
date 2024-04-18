#include <Python.h>
#include <stdbool.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>

#if defined(_WIN32) | defined(_WIN64)
#include <winsock2.h>
#pragma comment(lib, "Ws2_32.lib")
#else
#include <arpa/inet.h>
#endif

#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <numpy/arrayobject.h>

void capsule_cleanup(PyObject *capsule) {
    void *memory = PyCapsule_GetPointer(capsule, NULL);
    free(memory);
}

uint16_t read_big_uint16(uint8_t *buff, size_t *pos) {
    uint16_t val = ntohs(*(uint16_t *)(buff + *pos));
    *pos += 2;
    return val;
}

uint32_t read_big_uint32(uint8_t *buff, size_t *pos) {
    uint32_t val = ntohl(*(uint32_t *)(buff + *pos));
    *pos += 4;
    return val;
}

uint16_t read_little_uint16(uint8_t *buff, size_t *pos) {
    uint16_t val = *(uint16_t *)(buff + *pos);
    *pos += 2;
    return val;
}

uint32_t read_little_uint32(uint8_t *buff, size_t *pos) {
    uint32_t val = *(uint32_t *)(buff + *pos);
    *pos += 4;
    return val;
}

int16_t read_little_int16(uint8_t *buff, size_t *pos) {
    int16_t val = *(int16_t *)(buff + *pos);
    *pos += 2;
    return val;
}

int32_t read_little_int32(uint8_t *buff, size_t *pos) {
    int32_t val = *(int32_t *)(buff + *pos);
    *pos += 4;
    return val;
}

PyObject *py_test(PyObject *self, PyObject *args) {
    printf("Hello from C!\n");
    return PyUnicode_FromString("Hello. I'm a C function.");
}

PyObject *py_decode_uv_delta(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"file", "data_offset", "num_times", "num_wavelengths", NULL};
    uint32_t data_offset, num_times, num_wavelengths;
    PyObject *f;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OIII", kwlist, &f, &data_offset, &num_times, &num_wavelengths)) {
        PyErr_SetString(PyExc_TypeError, "Invalid arguments");
        return NULL;
    }

    PyObject *f_fileno = PyObject_CallNoArgs(PyObject_GetAttrString(f, "fileno"));
    int fd = PyLong_AsLong(f_fileno);

    // Get the file size with stat
    struct stat st;
    fstat(fd, &st);
    off_t file_size = st.st_size;
    off_t curr_pos = lseek(fd, 0, SEEK_CUR);
    void *buff = malloc(file_size);
    // read whole files into buff
    lseek(fd, 0, SEEK_SET);
    read(fd, buff, file_size);

    size_t pos = data_offset;

    uint32_t *times_array = malloc(num_times * sizeof(uint32_t));
    int64_t *data_array = malloc(num_times * num_wavelengths * sizeof(int64_t));

    for (uint32_t i=0; i<num_times; i++) {
        pos += 4;
        times_array[i] = read_little_uint32(buff, &pos);
        pos += 14;

        int64_t absorb_accum = 0;
        for (uint32_t j=0; j<num_wavelengths; j++) {
            int16_t check_int = read_little_int16(buff, &pos);
            if (check_int == -0x8000) {
                absorb_accum = read_little_int32(buff, &pos);
            } else {
                absorb_accum += check_int;
            }
            data_array[i * num_wavelengths + j] = absorb_accum;
        }
    }
    free(buff);

    npy_intp dims[2] = {num_times, num_wavelengths};
    PyObject *capsule;
    PyObject *data = PyArray_SimpleNewFromData(2, dims, NPY_INT64, (void *)data_array);
    capsule = PyCapsule_New(data_array, NULL, capsule_cleanup);
    PyArray_SetBaseObject((PyArrayObject *)data, capsule);
    PyObject *times = PyArray_SimpleNewFromData(1, dims, NPY_UINT32, (void *)times_array);
    capsule = PyCapsule_New(times_array, NULL, capsule_cleanup);
    PyArray_SetBaseObject((PyArrayObject *)times, capsule);

    lseek(fd, curr_pos, SEEK_SET);
    return PyTuple_Pack(2, times, data);
}

uint32_t bisect(double *array, uint32_t size, double value) {
    uint32_t low = 0;
    uint32_t high = size;
    while (low < high) {
        uint32_t mid = (low + high) / 2;
        if (array[mid] < value) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }
    return low;
}

uint64_t decode_intensity(uint16_t intensity) {
    uint32_t mantissa = intensity & 0x3FFF;
    uint32_t exponent = intensity >> 14;
    return ((uint64_t)1 << (3 * exponent)) * mantissa;
}

int compare_uint16_t(const void* a, const void* b) {
    uint16_t arg1 = *(const uint16_t*) a;
    uint16_t arg2 = *(const uint16_t*) b;

    if (arg1 < arg2) return -1;
    if (arg1 > arg2) return 1;
    return 0;
}

int compare_double_t(const void* a, const void* b) {
    double arg1 = *(const double*) a;
    double arg2 = *(const double*) b;

    if (arg1 < arg2) return -1;
    if (arg1 > arg2) return 1;
    return 0;
}

//PyObject *py_decode_ms(PyObject *self, PyObject *args, PyObject *kwargs) {
//    // takes f, data_offest
//    uint32_t data_offset, num_times, prec=0;
//    PyObject *f;
//    static char *kwlist[] = {"file", "data_offset", "num_times", "prec", NULL};
//
//    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OIII", kwlist, &f, &data_offset, &num_times, &prec)) {
//        PyErr_SetString(PyExc_TypeError, "Invalid arguments");
//        return NULL;
//    }
//    double round_fac = pow(10, prec);
//    PyObject *f_fileno = PyObject_CallNoArgs(PyObject_GetAttrString(f, "fileno"));
//    int fd = PyLong_AsLong(f_fileno);
//    printf("fd: %d, data_offset: %d, num_times: %d\n", fd, data_offset, num_times);
//    struct stat st;
//    fstat(fd, &st);
//    off_t file_size = st.st_size;
//    // mmap the file
//    void *file = mmap(NULL, file_size, PROT_READ, MAP_PRIVATE, fd, 0);
//    size_t pos = data_offset;
//    size_t start_pos = read_big_uint16(file, &pos) * 2 - 2;
//    pos = start_pos;
//
//    double times[num_times];
//    uint16_t pair_counts[num_times];
//    size_t pair_locs[num_times];
//
//    uint32_t total_pair_count = 0;
//    // Read just the times and pair counts
//    for(uint32_t i=0; i<num_times; i++) {
//        pos += 2;
//        times[i] = read_big_uint32(file, &pos) / 60000.;
//        pos += 6;
//        uint16_t pair_count = read_big_uint16(file, &pos);
//        pair_locs[i] = pos + 4;
//        // We'll read the data at this pos later
//        pair_counts[i] = pair_count;
//        total_pair_count += pair_count;
//        pos += 4 + pair_count * 4 + 10;
//    }
//
//    double mzs[total_pair_count];
//    uint64_t intensities[total_pair_count];
//
//    for(uint32_t i=0; i<num_times; i++) {
//        pos = pair_locs[i];
//        uint16_t pair_count = pair_counts[i];
//        for(int j=0; j<pair_count; j++) {
//            uint16_t index = i * pair_count + j;
//            mzs[index] = round(read_big_uint16(file, &pos) / 20.0 * round_fac) / round_fac;
//            intensities[index] = decode_intensity(read_big_uint16(file, &pos));
//        }
//    }
//    double sorted_mzs[total_pair_count];
//    memcpy(sorted_mzs, mzs, total_pair_count * sizeof(double));
//    qsort(sorted_mzs, total_pair_count, sizeof(double), compare_double_t);
//    double unique_mzs[total_pair_count];
//    uint32_t unique_mzs_count = 0;
//
//    unique_mzs[0] = sorted_mzs[0];
//    for (uint32_t i=1; i<total_pair_count; i++) {
//        if (sorted_mzs[i] != sorted_mzs[i-1]) {
//            unique_mzs[++unique_mzs_count] = sorted_mzs[i];
//        }
//    }
//
//    double data[num_times * unique_mzs_count];
//    for (uint32_t i=0; i<num_times * unique_mzs_count; i++) {
//        data[i] = 0;
//    }
//    uint16_t curr_index = 0;
//    for(uint32_t i=0; i<num_times; i++) {
//        uint16_t stop_index = curr_index + pair_counts[i];
//        for(int j=curr_index; j<stop_index; j++) {
//            int mz_index = bisect(unique_mzs, unique_mzs_count, mzs[j]);
//            data[i * unique_mzs_count + mz_index] += intensities[j];
//        }
//        curr_index = stop_index;
//    }
//
//    npy_intp dims[2] = {num_times, unique_mzs_count};
//    PyObject *data_array = PyArray_SimpleNewFromData(2, dims, NPY_DOUBLE, (void *)data);
//
//    PyObject *times_array = PyArray_SimpleNewFromData(1, dims, NPY_DOUBLE, (void *)times);
//    dims[1] = unique_mzs_count;
//    PyObject *ylabels_array = PyArray_SimpleNewFromData(1, dims, NPY_DOUBLE, (void *)unique_mzs);
//
//    // Return a tuple of times, ylabels, and data
//    return PyTuple_Pack(3, times_array, ylabels_array, data_array);
//}

static PyMethodDef methods[] = {
    {"test", (PyCFunction)py_test, METH_NOARGS, "Test"},
    {"decode_uv_delta", (PyCFunction)py_decode_uv_delta, METH_VARARGS | METH_KEYWORDS, "Decode UV Delta"},
//    {"decode_ms", (PyCFunction)py_decode_ms, METH_VARARGS | METH_KEYWORDS, "Decode MS"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef rainbow_module = {
    PyModuleDef_HEAD_INIT,
    "_rainbow",                              
    NULL,  
    -1,                                   
    methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC PyInit__rainbow() {
    import_array();
    return PyModule_Create(&rainbow_module);
};
