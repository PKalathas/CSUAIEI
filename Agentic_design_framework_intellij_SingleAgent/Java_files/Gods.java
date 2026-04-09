public class Gods extends Spirits{

    public void interactionH(Human myHuman){
        myHuman.setHealth(100);
    }
    public void interactionC(Creature myCreature){

    }
    public void interactionA(Animal myAnimal){
        myAnimal.setHealth(100);
    }
}
