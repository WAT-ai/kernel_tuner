"""This module contains all HIP specific kernel_tuner functions"""

import numpy as np
import ctypes as C
from collections import namedtuple

from kernel_tuner.backends.backend import GPUBackend

# embedded in try block to be able to generate documentation
# and run tests without pyhip installed
try:
    from pyhip import hip, hiprtc
except ImportError:
    hip = None
    hiprtc = None

dtype_map = {
    "int8": C.c_int8,
    "int16": C.c_int16,
    "int32": C.c_int32,
    "int64": C.c_int64,
    "uint8": C.c_uint8,
    "uint16": C.c_uint16,
    "uint32": C.c_uint32,
    "uint64": C.c_uint64,
    "float32": C.c_float,
    "float64": C.c_double,
}

# This represents an individual kernel argument.
# It contains a numpy object (ndarray or number) and a ctypes object with a copy
# of the argument data. For an ndarray, the ctypes object is a wrapper for the ndarray's data.
Argument = namedtuple("Argument", ["numpy", "ctypes"])

class HipFunctions(GPUBackend):
    """Class that groups the HIP functions on maintains state about the device"""

    def __init__(self, device=0, iterations=7, compiler_options=None, observers=None):
        """instantiate HipFunctions object used for interacting with the HIP device

        Instantiating this object will inspect and store certain device properties at
        runtime, which are used during compilation and/or execution of kernels by the
        kernel tuner. It also maintains a reference to the most recently compiled
        source module for copying data to constant memory before kernel launch.

        :param device: Number of HIP device to use for this context
        :type device: int

        :param iterations: Number of iterations used while benchmarking a kernel, 7 by default.
        :type iterations: int
        """

    def ready_argument_list(self, arguments):
        """ready argument list to be passed to the HIP function
        :param arguments: List of arguments to be passed to the HIP function.
            The order should match the argument list on the HIP function.
            Allowed values are np.ndarray, and/or np.int32, np.float32, and so on.
        :type arguments: list(numpy objects)
        :returns: A list of arguments that can be passed to the HIP function.
        :rtype: list(Argument)
        """
        ctype_args = [None for _ in arguments]

        for i, arg in enumerate(arguments):
            if not isinstance(arg, (np.ndarray, np.number)):
                raise TypeError(
                    "Argument is not numpy ndarray or numpy scalar %s" % type(arg)
                )
            dtype_str = str(arg.dtype)
            if isinstance(arg, np.ndarray):
                if dtype_str in dtype_map.keys():
                    # In numpy <= 1.15, ndarray.ctypes.data_as does not itself keep a reference
                    # to its underlying array, so we need to store a reference to arg.copy()
                    # in the Argument object manually to avoid it being deleted.
                    # (This changed in numpy > 1.15.)
                    # data_ctypes = data.ctypes.data_as(C.POINTER(dtype_map[dtype_str]))
                    data_ctypes = arg.ctypes.data_as(C.POINTER(dtype_map[dtype_str]))
                else:
                    raise TypeError("unknown dtype for ndarray")
            elif isinstance(arg, np.generic):
                data_ctypes = dtype_map[dtype_str](arg)
            ctype_args[i] = Argument(numpy=arg, ctypes=data_ctypes)
        return ctype_args
    
    def compile(self, kernel_instance):
        """call the HIP compiler to compile the kernel, return the function
        
        :param kernel_instance: An object representing the specific instance of the tunable kernel
            in the parameter space.
        :type kernel_instance: kernel_tuner.core.KernelInstance
        
        :returns: An ctypes function that can be called directly.
        :rtype: ctypes._FuncPtr
        """

        kernel_string = kernel_instance.kernel_string
        kernel_name = kernel_instance.name
        kernel_ptr = hiprtc.hiprtcCreateProgram(kernel_string, kernel_name, [], [])
        
        device_properties = hip.hipGetDeviceProperties(0)
        hiprtc.hiprtcCompileProgram(kernel_ptr, [f'--offload-arch={device_properties.gcnArchName}'])
        code = hiprtc.hiprtcGetCode(kernel_ptr)
        module = hip.hipModuleLoadData(code)
        kernel = hip.hipModuleGetFunction(module, kernel_name)
        
        return kernel