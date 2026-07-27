from typing import Type, TypeVar, Callable, Any, Dict
from core.exceptions import ConfigurationError

T = TypeVar('T')

class ServiceLocator:
    """Dependency Injection container supporting singleton and lazy initialization."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services = {}
            cls._instance._factories = {}
            cls._instance._singletons = {}
        return cls._instance

    @classmethod
    def register(cls, interface: Type[T], implementation: Any, singleton: bool = True, lazy: bool = False):
        instance = cls()
        if lazy:
            if not callable(implementation):
                raise ConfigurationError("Lazy registration requires a callable factory.")
            instance._factories[interface] = implementation
            instance._singletons[interface] = singleton
        else:
            if singleton:
                if callable(implementation) and isinstance(implementation, type):
                    instance._services[interface] = implementation()
                else:
                    instance._services[interface] = implementation
            else:
                if not callable(implementation):
                    raise ConfigurationError("Transient registration requires a callable factory or type.")
                instance._factories[interface] = implementation if not isinstance(implementation, type) else lambda: implementation()
                instance._singletons[interface] = False

    @classmethod
    def resolve(cls, interface: Type[T]) -> T:
        instance = cls()
        if interface in instance._services:
            return instance._services[interface]
        
        if interface in instance._factories:
            factory = instance._factories[interface]
            obj = factory()
            if instance._singletons.get(interface, False):
                instance._services[interface] = obj
            return obj
            
        raise ConfigurationError(f"Service not registered for {interface}")

    @classmethod
    def replace(cls, interface: Type[T], implementation: Any, singleton: bool = True, lazy: bool = False):
        cls.remove(interface)
        cls.register(interface, implementation, singleton=singleton, lazy=lazy)

    @classmethod
    def remove(cls, interface: Type[T]):
        instance = cls()
        instance._services.pop(interface, None)
        instance._factories.pop(interface, None)
        instance._singletons.pop(interface, None)

def resolve(interface: Type[T]) -> T:
    """Helper method to resolve services."""
    return ServiceLocator.resolve(interface)
